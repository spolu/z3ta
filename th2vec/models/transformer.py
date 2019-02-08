import torch
import torch.nn as nn

from generic.gelu import GeLU
from generic.layer_norm import LayerNorm
from generic.transformer import Transformer, Downsample, Upsample

from torch.distributions.categorical import Categorical


class P(nn.Module):
    """ Direct Premiser
    """
    def __init__(
            self,
            config,
    ):
        super(P, self).__init__()

        self.device = torch.device(config.get('device'))

        self.token_count = \
            config.get('th2vec_token_count')
        self.theorem_length = \
            config.get('th2vec_theorem_length')
        self.embedding_size = \
            config.get('th2vec_transformer_embedding_size')
        self.hidden_size = \
            config.get('th2vec_transformer_hidden_size')
        self.intermediate_size = \
            config.get('th2vec_transformer_intermediate_size')
        self.attention_head_count = \
            config.get('th2vec_transformer_attention_head_count')
        self.layer_count = \
            config.get('th2vec_transformer_layer_count')

        self.input_embedding = nn.Embedding(
            self.token_count, self.embedding_size,
        )
        self.position_embedding = nn.Embedding(
            self.theorem_length, self.embedding_size
        )

        layers = []
        layers += [
            nn.Linear(self.embedding_size, self.hidden_size),
        ]

        for _ in range(self.layer_count):
            layers += [
                Transformer(
                    self.hidden_size,
                    self.attention_head_count,
                    self.intermediate_size,
                    dropout=0.1,
                ),
            ]

        self.layers = nn.Sequential(*layers)

        self.inner_cnj = nn.Sequential(*[
            nn.Linear(self.hidden_size, self.hidden_size),
            GeLU(),
            nn.Dropout(0.1),
            LayerNorm(self.hidden_size),
        ])
        self.inner_thr = nn.Sequential(*[
            nn.Linear(self.hidden_size, self.hidden_size),
            GeLU(),
            nn.Dropout(0.1),
            LayerNorm(self.hidden_size),
        ])

        self.head = nn.Sequential(*[
            nn.Linear(2*self.hidden_size, self.hidden_size),
            GeLU(),
            nn.Dropout(0.1),
            LayerNorm(self.hidden_size),
            nn.Linear(self.hidden_size, 1),
            nn.Sigmoid(),
        ])

    def parameters_count(model):
        return sum(p.numel() for p in model.parameters() if p.requires_grad)

    def th2vec(
            self,
            embeds,
    ):
        hiddens = self.layers(embeds)

        return torch.tanh(
            # torch.mean(hiddens, 1)
            torch.max(hiddens, 1)[0]
        )

    def forward(
            self,
            conjecture,
            theorem,
    ):
        pos_embeds = torch.arange(
            self.theorem_length, dtype=torch.long
        ).to(self.device)
        pos_embeds = pos_embeds.unsqueeze(0).expand(
           conjecture.size(0), self.theorem_length,
        )
        pos_embeds = self.position_embedding(pos_embeds)

        cnj_embeds = self.input_embedding(conjecture)
        thr_embeds = self.input_embedding(theorem)

        cnj_th2vec = self.th2vec(cnj_embeds + pos_embeds)
        thr_th2vec = self.th2vec(thr_embeds + pos_embeds)

        return self.head(
            torch.cat(
                (self.inner_cnj(cnj_th2vec), self.inner_thr(thr_th2vec)),
                dim=1,
            )
        )


class E(nn.Module):
    """ Embedder
    """
    def __init__(
            self,
            config,
    ):
        super(E, self).__init__()

        self.device = torch.device(config.get('device'))

        self.token_count = \
            config.get('th2vec_token_count')
        self.theorem_length = \
            config.get('th2vec_theorem_length')
        self.embedding_size = \
            config.get('th2vec_transformer_embedding_size')
        self.hidden_size = \
            config.get('th2vec_transformer_hidden_size')
        self.intermediate_size = \
            config.get('th2vec_transformer_intermediate_size')
        self.attention_head_count = \
            config.get('th2vec_transformer_attention_head_count')
        self.layer_count = \
            config.get('th2vec_transformer_layer_count')

        self.input_embedding = nn.Embedding(
            self.token_count, self.embedding_size,
        )
        self.position_embedding = nn.Embedding(
            self.theorem_length, self.embedding_size
        )

        layers = []
        layers += [
            LayerNorm(self.embedding_size),
            nn.Linear(self.embedding_size, self.hidden_size),
        ]

        for _ in range(self.layer_count):
            layers += [
                Transformer(
                    self.hidden_size,
                    self.attention_head_count,
                    self.intermediate_size,
                    dropout=0.1,
                ),
            ]

        n = self.theorem_length
        while n > 1:
            layers += [
                Downsample(self.hidden_size, 2, 2),
                GeLU(),
                nn.Dropout(0.1),
                LayerNorm(self.hidden_size),
            ]
            n = n // 2

        self.layers = nn.Sequential(*layers)

    def parameters_count(model):
        return sum(p.numel() for p in model.parameters() if p.requires_grad)

    def forward(
            self,
            term,
    ):
        pos_embeds = torch.arange(
            self.theorem_length, dtype=torch.long
        ).to(self.device)
        pos_embeds = pos_embeds.unsqueeze(0).expand(
           term.size(0), self.theorem_length,
        )
        pos_embeds = self.position_embedding(pos_embeds)

        trm_embeds = self.input_embedding(term)

        return torch.tanh(
            self.layers(trm_embeds + pos_embeds).squeeze(1),
            # torch.max(self.layers(trm_embeds + pos_embeds), 1)[0],
        )


class G(nn.Module):
    """ Generator
    """
    def __init__(
            self,
            config,
    ):
        super(G, self).__init__()

        self.device = torch.device(config.get('device'))

        self.token_count = \
            config.get('th2vec_token_count')
        self.theorem_length = \
            config.get('th2vec_theorem_length')
        self.embedding_size = \
            config.get('th2vec_transformer_embedding_size')
        self.hidden_size = \
            config.get('th2vec_transformer_hidden_size')
        self.intermediate_size = \
            config.get('th2vec_transformer_intermediate_size')
        self.attention_head_count = \
            config.get('th2vec_transformer_attention_head_count')
        self.layer_count = \
            config.get('th2vec_transformer_layer_count')

        layers = []
        layers += [
        ]

        n = self.theorem_length
        while n > 1:
            layers += [
                Upsample(self.hidden_size, 2, 2),
                GeLU(),
                nn.Dropout(0.1),
                LayerNorm(self.hidden_size),
            ]
            n = n // 2

        for _ in range(self.layer_count):
            layers += [
                Transformer(
                    self.hidden_size,
                    self.attention_head_count,
                    self.intermediate_size,
                    dropout=0.1,
                ),
            ]

        layers += [
            nn.Linear(self.hidden_size, self.token_count),
            nn.LogSoftmax(dim=2),
        ]

        self.layers = nn.Sequential(*layers)

    def parameters_count(model):
        return sum(p.numel() for p in model.parameters() if p.requires_grad)

    def forward(
            self,
            hidden,
    ):
        return self.layers(hidden.unsqueeze(1))

    def sample(
            self,
            reconstruct,
    ):
        m = Categorical(torch.exp(reconstruct))
        return m.sample()


class D(nn.Module):
    """ Discriminator
    """
    def __init__(
            self,
            config,
    ):
        super(D, self).__init__()

        self.device = torch.device(config.get('device'))

        self.token_count = \
            config.get('th2vec_token_count')
        self.theorem_length = \
            config.get('th2vec_theorem_length')
        self.embedding_size = \
            config.get('th2vec_transformer_embedding_size')
        self.hidden_size = \
            config.get('th2vec_transformer_hidden_size')
        self.intermediate_size = \
            config.get('th2vec_transformer_intermediate_size')
        self.attention_head_count = \
            config.get('th2vec_transformer_attention_head_count')
        self.layer_count = \
            config.get('th2vec_transformer_layer_count')

        self.input_embedding = nn.Embedding(
            self.token_count, self.embedding_size,
        )
        self.position_embedding = nn.Embedding(
            self.theorem_length, self.embedding_size
        )

        layers = []
        layers += [
            LayerNorm(self.embedding_size),
            nn.Linear(self.embedding_size, self.hidden_size),
        ]

        for _ in range(self.layer_count):
            layers += [
                Transformer(
                    self.hidden_size,
                    self.attention_head_count,
                    self.intermediate_size,
                    dropout=0.1,
                ),
            ]

        n = self.theorem_length
        while n > 2:
            layers += [
                Downsample(self.hidden_size, 2, 2),
                GeLU(),
                nn.Dropout(0.1),
                LayerNorm(self.hidden_size),
            ]
            n = n // 2

        layers += [
            nn.Linear(self.hidden_size, self.hidden_size),
            GeLU(),
            nn.Dropout(0.1),
            LayerNorm(self.hidden_size),
            nn.Linear(self.hidden_size, 1),
            nn.Sigmoid(),
        ]

        self.layers = nn.Sequential(*layers)

    def parameters_count(model):
        return sum(p.numel() for p in model.parameters() if p.requires_grad)

    def forward(
            self,
            term,
    ):
        pos_embeds = torch.arange(
            self.theorem_length, dtype=torch.long
        ).to(self.device)
        pos_embeds = pos_embeds.unsqueeze(0).expand(
           term.size(0), self.theorem_length,
        )
        pos_embeds = self.position_embedding(pos_embeds)

        trm_embeds = self.input_embedding(term)

        return torch.tanh(
            self.layers(trm_embeds + pos_embeds).squeeze(1),
            # torch.max(self.layers(trm_embeds + pos_embeds), 1)[0],
        )

