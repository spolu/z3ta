import os
import random
import torch

from torch.utils.data import Dataset

from utils.log import Log


class HolStepKernel():
    def __init__(
            self,
            theorem_length: int,
    ) -> None:
        self._compression = {}

        self._tokens = {}
        # self._invert = {}
        self._token_count = 1

        self._chars = {}
        self._char_count = 1

        self._theorem_length = theorem_length

    def process_raw_formula(
            self,
            f: str,
    ):
        formula = []

        for c in f:
            if c not in self._chars:
                self._chars[c] = self._char_count
                self._char_count += 1

            formula.append(self._chars[c])

        return formula

    def process_tokenized_formula(
            self,
            f: str,
    ):
        formula = []
        tokens = f.split(' ')

        for t in tokens:
            if t not in self._tokens:
                self._tokens[t] = self._token_count
                # self._invert[self._token_count] = t
                self._token_count += 1

            formula.append(self._tokens[t])

        # for i in range(len(formula)):
        #     for j in range(1, 3):
        #         if i + j < len(formula):
        #             ngram = self.detokenize(formula[i:i+j+1])
        #             if ngram not in self._compression:
        #                 self._compression[ngram] = 0
        #             self._compression[ngram] += j

        return formula

    # def postprocess_compression(
    #         self,
    #         size: int,
    # ) -> None:
    #     best = sorted(
    #         self._compression.keys(),
    #         key=lambda ngram: self._compression[ngram],
    #         reverse=True,
    #     )

    #     for i in range(size):
    #         # Should not be any collision on `detokenize(formula[i:i+j+1])`
    #         self._tokens[best[i]] = self._token_count
    #         self._invert[self._token_count] = best[i]
    #         self._token_count += 1

    # def postprocess_formula(
    #         self,
    #         f,
    # ):
    #     formula = []

    #     i = 0
    #     while i < len(f):
    #         done = False
    #         for j in reversed(range(1, 3)):
    #             if i + j < len(f):
    #                 ngram = self.detokenize(f[i:i+j+1])
    #                 if ngram in self._tokens:
    #                     formula.append(self._tokens[ngram])
    #                     i += j+1
    #                     done = True
    #                     break
    #         if not done:
    #             formula.append(f[i])
    #             i += 1

    #     return formula

    def detokenize(
            self,
            tokenized,
    ):
        term = ""

        for i in range(len(tokenized)):
            v = tokenized[i]
            if v == 0:
                term += "__"
            elif v not in self._invert:
                term += " ?"
            else:
                term += " " + self._invert[v]

        if len(term) > 0:
            term = term[1:]

        return term


class HolStepSet():
    def __init__(
            self,
            kernel: HolStepKernel,
            dataset_dir: str,
            raw_formula: bool = False,
            premise_only: bool = False,
    ) -> None:
        self._kernel = kernel
        self._raw_formula = raw_formula
        self._premise_only = premise_only

        # The actual tokenized formulas.
        self._formulas = []
        self._max_length = 0

        # All conjectures.
        self._C = []
        # Conjectures with premises (should be all).
        self._C_premise = []
        # Conjectures with proof steps.
        self._C_step = []
        # All premises to conjectures.
        self._T = []
        # Premises for a conjecture in `self._C_premise`.
        self._D = {}
        # Positive proof steps for a conjecture in `self._C_step`.
        self._P = {}
        # Negative proof steps for a conjecture in `self._C_step`.
        self._N = {}

        dataset_dir = os.path.abspath(dataset_dir)

        Log.out(
            "Loading HolStep dataset", {
                'dataset_dir': dataset_dir,
            })

        assert os.path.isdir(dataset_dir)
        files = [
            os.path.join(dataset_dir, f)
            for f in os.listdir(dataset_dir)
            if os.path.isfile(os.path.join(dataset_dir, f))
        ]

        count = 0
        for p in files:
            count += 1
            self.process_file(p)

            if count % 100 == 0:
                Log.out(
                    "PreProcessing HolStep dataset", {
                        'dataset_dir': dataset_dir,
                        'token_count': self._kernel._token_count,
                        'char_count': self._kernel._char_count,
                        'max_length': self._max_length,
                        'formula_count': len(self._formulas),
                        'theorem_count': len(self._T),
                        'conjecture_count': len(self._C),
                        'processed': count,
                    })

        Log.out(
            "Loaded HolStep dataset", {
                'dataset_dir': dataset_dir,
                'token_count': self._kernel._token_count,
                'char_count': self._kernel._char_count,
                'max_length': self._max_length,
                'formula_count': len(self._formulas),
                'theorem_count': len(self._T),
                'conjecture_count': len(self._C),
            })

    def process_file(
            self,
            path,
    ):
        with open(path, 'r') as f:
            lines = f.read().splitlines()

            c_idx = None
            has_premise = False
            has_step = False

            for i in range(len(lines)):
                line = lines[i]
                if line[0] == 'T':
                    if self._premise_only and (
                            lines[i-1][0] != 'C' and
                            lines[i-1][0] != 'A'
                    ):
                        continue

                    f = None
                    if self._raw_formula:
                        f = self._kernel.process_raw_formula(lines[i-1][2:])
                    else:
                        f = self._kernel.process_tokenized_formula(line[2:])
                    assert f is not None

                    f_idx = len(self._formulas)
                    self._formulas.append(f)

                    self._max_length = max(self._max_length, len(f))
                    if len(f) > self._kernel._theorem_length:
                        Log.out("Excessive length formula", {
                            'length': len(f),
                        })

                    if lines[i-1][0] == 'C':
                        c_idx = f_idx
                        self._C.append(c_idx)
                        self._D[c_idx] = []
                        self._P[c_idx] = []
                        self._N[c_idx] = []

                    assert c_idx is not None

                    if lines[i-1][0] == 'A':
                        self._D[c_idx].append(f_idx)
                        has_premise = True
                        self._T.append(f_idx)
                    if lines[i-1][0] == '+':
                        self._P[c_idx].append(f_idx)
                        has_step = True
                    if lines[i-1][0] == '-':
                        self._N[c_idx].append(f_idx)

            if has_step:
                self._C_step.append(c_idx)
                assert len(self._P[c_idx]) > 0
                assert len(self._N[c_idx]) > 0
            if has_premise:
                self._C_premise.append(c_idx)

            assert has_premise

    # def postprocess(
    #         self,
    # ) -> None:
    #     Log.out("Postprocessing HolStep dataset", {})

    #     self._max_length = 0
    #     for i in range(len(self._formulas)):
    #         self._formulas[i] = self._kernel.postprocess_formula(
    #             self._formulas[i],
    #         )
    #         if len(self._formulas[i]) > self._max_length:
    #             self._max_length = len(self._formulas[i])
    #         if len(self._formulas[i]) > self._kernel._theorem_length:
    #             Log.out("Excessive length formula", {
    #                 'length': len(self._formulas[i]),
    #             })

    #         if i % 100000 == 0:
    #             Log.out("Postprocessing HolStep dataset", {
    #                 'token_count': self._kernel._token_count,
    #                 'max_length': self._max_length,
    #                 'formula_count': len(self._formulas),
    #                 'postprocessed': i,
    #             })

    #     Log.out("Postprocessed HolStep dataset", {
    #         'max_length': self._max_length,
    #     })


# PREMISER


class HolStepPremiseDataset(Dataset):
    def __init__(
            self,
            hset: HolStepSet,
    ) -> None:
        self._hset = hset
        self._theorem_length = hset._kernel._theorem_length

    def __len__(
            self,
    ) -> int:
        return 2*len(self._hset._C_premise)

    def __getitem__(
            self,
            idx: int,
    ):
        cnj_t = torch.zeros(self._theorem_length, dtype=torch.int64)
        thr_t = torch.zeros(self._theorem_length, dtype=torch.int64)
        pre_t = torch.ones(1)

        cnj = self._hset._C_premise[int(idx/2)]
        thr = random.choice(self._hset._D[cnj])

        if idx % 2 == 1:
            pre_t = torch.zeros(1)
            unr = None
            while(unr is None):
                candidate = random.choice(self._hset._T)
                if candidate not in self._hset._D[cnj]:
                    unr = candidate
            thr = unr

        for i in range(
                min(self._theorem_length, len(self._hset._formulas[cnj]))
        ):
            t = self._hset._formulas[cnj][i]
            assert t != 0
            cnj_t[i] = t
        for i in range(
                min(self._theorem_length, len(self._hset._formulas[thr]))
        ):
            t = self._hset._formulas[thr][i]
            assert t != 0
            thr_t[i] = t

        return cnj_t, thr_t, pre_t


class HolStepClassificationDataset(Dataset):
    def __init__(
            self,
            hset: HolStepSet,
    ) -> None:
        self._hset = hset
        self._theorem_length = hset._kernel._theorem_length
        assert hset._premise_only is False

    def __len__(
            self,
    ) -> int:
        return 2*len(self._hset._C_step)

    def __getitem__(
            self,
            idx: int,
    ):
        cnj_t = torch.zeros(self._theorem_length, dtype=torch.int64)
        thr_t = torch.zeros(self._theorem_length, dtype=torch.int64)
        pre_t = torch.ones(1)

        cnj = self._hset._C_step[int(idx/2)]
        thr = random.choice(self._hset._P[cnj])

        if idx % 2 == 1:
            pre_t = torch.zeros(1)
            thr = random.choice(self._hset._N[cnj])

        for i in range(
                min(self._theorem_length, len(self._hset._formulas[cnj]))
        ):
            t = self._hset._formulas[cnj][i]
            assert t != 0
            cnj_t[i] = t
        for i in range(
                min(self._theorem_length, len(self._hset._formulas[thr]))
        ):
            t = self._hset._formulas[thr][i]
            assert t != 0
            thr_t[i] = t

        return cnj_t, thr_t, pre_t


class HolStepPremisePairDataset(Dataset):
    def __init__(
            self,
            hset: HolStepSet,
    ) -> None:
        self._hset = hset
        self._theorem_length = hset._kernel._theorem_length

    def __len__(
            self,
    ) -> int:
        return len(self._hset._C_premise)

    def __getitem__(
            self,
            idx: int,
    ):
        cnj_t = torch.zeros(self._theorem_length, dtype=torch.int64)
        thr_t = torch.zeros(self._theorem_length, dtype=torch.int64)
        unr_t = torch.zeros(self._theorem_length, dtype=torch.int64)

        cnj = self._hset._C_premise[int(idx/2)]
        thr = random.choice(self._hset._D[cnj])

        unr = None
        while(unr is None):
            candidate = random.choice(self._hset._T)
            if candidate not in self._hset._D[cnj]:
                unr = candidate

        for i in range(
                min(self._theorem_length, len(self._hset._formulas[cnj]))
        ):
            t = self._hset._formulas[cnj][i]
            assert t != 0
            cnj_t[i] = t
        for i in range(
                min(self._theorem_length, len(self._hset._formulas[thr]))
        ):
            t = self._hset._formulas[thr][i]
            assert t != 0
            thr_t[i] = t
        for i in range(
                min(self._theorem_length, len(self._hset._formulas[unr]))
        ):
            t = self._hset._formulas[unr][i]
            assert t != 0
            unr_t[i] = t

        return cnj_t, thr_t, unr_t


class HolStepTermDataset(Dataset):
    def __init__(
            self,
            hset: HolStepSet,
    ) -> None:
        self._hset = hset
        self._theorem_length = hset._kernel._theorem_length

    def __len__(
            self,
    ) -> int:
        return len(self._hset._formulas)

    def __getitem__(
            self,
            idx: int,
    ):
        trm_t = torch.zeros(self._theorem_length, dtype=torch.int64)

        for i in range(
                min(self._theorem_length, len(self._hset._formulas[idx]))
        ):
            t = self._hset._formulas[idx][i]
            assert t != 0
            trm_t[i] = t

        return trm_t


def preprocess():
    kernel = HolStepKernel(512)

    HolStepSet(
        kernel,
        os.path.expanduser("./data/th2vec/holstep/train"),
        premise_only=False,
        raw_formula=True,
    )
    HolStepSet(
        kernel,
        os.path.expanduser("./data/th2vec/holstep/test"),
        premise_only=False,
        raw_formula=True,
    )

    # kernel.postprocess_compression(4096)
    # dataset.postprocess()
