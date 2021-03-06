import torch
import torch.nn as nn
import typing
import xxhash


class BVT():
    """ BVT stands for BinaryValuedTree
    """
    def __init__(
            self,
            value,
            left=None,
            right=None,
    ):
        self.value = value
        self.left = left
        self.right = right

        self._hash = None
        self._depth = None

    def hash(
            self,
    ):
        if self._hash is None:
            h = xxhash.xxh64()
            if isinstance(self.value, BVT):
                h.update(self.value.hash())
            else:
                h.update(str(self.value))
            if self.left is not None:
                h.update(self.left.hash())
            if self.right is not None:
                h.update(self.right.hash())
            self._hash = h.digest()

        return self._hash

    def depth(
            self,
    ):
        if self._depth is None:
            if self.left is not None:
                ld = self.left.depth()
            else:
                ld = -1
            if self.right is not None:
                rd = self.right.depth()
            else:
                rd = -1
            self._depth = 1 + max(ld, rd)

        return self._depth

    def string(
            self,
    ):
        string = str(self.value)

        if self.left is not None:
            string += self.left.string()
        else:
            string += 'N'
        if self.right is not None:
            string += self.right.string()
        else:
            string += 'N'

        return string


class BinaryTreeLSTM(nn.Module):
    """ Binary TreeLSTM with node values.

    BinaryTreeLSTM internalize the embedding of BVT values assumed to be
    integers.
    """
    def __init__(
            self,
            hidden_size,
    ):
        super(BinaryTreeLSTM, self).__init__()

        self.device = torch.device('cpu')

        self.hidden_size = hidden_size

        self.wx = nn.Linear(hidden_size, 5 * hidden_size)
        self.wh = nn.Linear(2 * hidden_size, 5 * hidden_size)

    def to(
            self,
            *args,
            **kwargs,
    ):
        device, _, _ = torch._C._nn._parse_to(*args, **kwargs)
        self.device = device

        return super(BinaryTreeLSTM, self).to(*args, **kwargs)

    def batch(
            self,
            trees: typing.List[BVT],
            embedder,
    ):
        """ Dynamic batching on an array of BVT

        Caching will perform better if the trees are sorted by depth. We can't
        easily do so here so it's just easier if callers ensure it.
        """
        V = []
        L = []
        R = []

        cache = {}
        counters = {
            'cache_hits': 0,
            'compute_steps': 0,
        }

        def dfs(tree, depth):
            if tree.hash() in cache and cache[tree.hash()][0] >= depth:
                counters['cache_hits'] += 1
                return cache[tree.hash()]
            counters['compute_steps'] += 1

            while depth >= len(V):
                V.append([])
                L.append([])
                R.append([])

            idx = len(V[depth])
            V[depth].append(tree.value)

            if tree.left is not None:
                L[depth].append(dfs(tree.left, depth+1))
            else:
                L[depth].append((depth+1, -1))
            if tree.right is not None:
                R[depth].append(dfs(tree.right, depth+1))
            else:
                R[depth].append((depth+1, -1))

            cache[tree.hash()] = (depth, idx)

            return (depth, idx)

        # Consturct the folded computation graph.
        pos = [dfs(t, 0) for t in trees]

        # Log.out("TreeLSTM dynamic batching", {
        #     "batch_size": len(trees),
        #     "compute_steps": counters['compute_steps'],
        #     "cache_hits": counters['cache_hits'],
        # })

        H = [[]] * len(V)
        C = [[]] * len(V)

        for d in reversed(range(len(V))):
            v = embedder(V[d])

            lh = []
            lc = []
            rh = []
            rc = []
            for i in range(len(V[d])):
                if L[d][i][1] > -1:
                    lh.append(H[L[d][i][0]][L[d][i][1]].unsqueeze(0))
                    lc.append(C[L[d][i][0]][L[d][i][1]].unsqueeze(0))
                else:
                    lh.append(torch.zeros(
                        1, self.hidden_size,
                    ).to(self.device))
                    lc.append(torch.zeros(
                        1, self.hidden_size,
                    ).to(self.device))
                if R[d][i][1] > -1:
                    rh.append(H[R[d][i][0]][R[d][i][1]].unsqueeze(0))
                    rc.append(C[R[d][i][0]][R[d][i][1]].unsqueeze(0))
                else:
                    rh.append(torch.zeros(
                        1, self.hidden_size,
                    ).to(self.device))
                    rc.append(torch.zeros(
                        1, self.hidden_size,
                    ).to(self.device))

            lh = torch.cat(lh, dim=0)
            lc = torch.cat(lc, dim=0)
            rh = torch.cat(rh, dim=0)
            rc = torch.cat(rc, dim=0)

            # assert v.size(0) == \
            #     lh.size(0) == lc.size(0) == \
            #     rh.size(0) == rc.size(0)

            h, c = self.forward(v, lh, lc, rh, rc)

            H[d] = h
            C[d] = c

        # At this stage everything is computed we just need to return the
        # top-level vectors for each tree.

        Ht = [[]] * len(pos)
        Ct = [[]] * len(pos)

        for i, p in enumerate(pos):
            Ht[i] = H[p[0]][p[1]].unsqueeze(0)
            Ct[i] = C[p[0]][p[1]].unsqueeze(0)

        Ht = torch.cat(Ht, dim=0)
        Ct = torch.cat(Ct, dim=0)

        assert Ht.size(0) == len(trees)

        return Ht, Ct

    def recurse(
            self,
            tree: BVT,
            embedder,
    ):
        left_h, left_c = None, None
        if tree.left is not None:
            left_h, left_c = self.recurse(tree.left, embedder)

        right_h, right_c = None, None
        if tree.right is not None:
            right_h, right_c = self.recurse(tree.right, embedder)

        if left_h is None:
            left_h, left_c = \
                (torch.zeros(
                    1, self.hidden_size,
                ).to(self.device),
                 torch.zeros(
                     1, self.hidden_size,
                 ).to(self.device))
        if right_h is None:
            right_h, right_c = \
                (torch.zeros(
                    1, self.hidden_size,
                ).to(self.device),
                 torch.zeros(
                     1, self.hidden_size,
                 ).to(self.device))

        return self.forward(
            embedder([tree.value]),
            left_h, left_c,
            right_h, right_c,
        )

    def forward(
            self,
            value,             # (hidden_size)
            left_h, left_c,    # (hidden_size)
            right_h, right_c,  # (hidden_size)
    ):
        # batch_size = value.size(0)
        # assert value.size() == torch.Size([batch_size, self.hidden_size])
        # assert left_h.size() == torch.Size([batch_size, self.hidden_size])
        # assert left_c.size() == torch.Size([batch_size, self.hidden_size])
        # assert right_h.size() == torch.Size([batch_size, self.hidden_size])
        # assert right_c.size() == torch.Size([batch_size, self.hidden_size])

        i, o, u, f1, f2 = (self.wx(value) + self.wh(
            torch.cat([left_h, right_h], dim=-1)
        )).chunk(5, -1)

        i, o = torch.sigmoid(i), torch.sigmoid(o)
        f1, f2 = torch.sigmoid(f1), torch.sigmoid(f2)
        u = torch.tanh(u)

        c = (i * u + f1 * left_c + f2 * right_c)
        h = o * torch.tanh(c)

        return h, c


def test():
    embedding = nn.Embedding(10, 4)

    def embedder(values):
        return embedding(
            torch.tensor(values, dtype=torch.int64).to(torch.device('cpu'))
        )

    tree_lstm = BinaryTreeLSTM(4)
    tree_lstm.to(torch.device('cpu'))
    trees = [
        BVT(0, BVT(2)),
        BVT(0, BVT(2, BVT(2), BVT(8, BVT(0))), BVT(3)),
        BVT(1),
        BVT(3, BVT(0, BVT(0), BVT(0)), BVT(0)),
        BVT(1),
    ]

    for i, t in enumerate(trees):
        e, _ = tree_lstm.recurse(t, embedder)
        print("{}: {}".format(i, e[0]))

    print("---")

    e, _ = tree_lstm.batch(trees, embedder)
    for i, t in enumerate(trees):
        print("{}: {} {}".format(i, e[i], trees[i].hash()))
