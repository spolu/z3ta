import torch
import torch.nn as nn

from generic.transformer import TransformerBlock


class H(nn.Module):
    def __init__(
            self,
            config,
    ):
        super(H, self).__init__()

        self.device = torch.device(config.get('device'))

        self.sequence_length = \
            config.get('prooftrace_sequence_length')
        self.hidden_size = \
            config.get('prooftrace_hidden_size')
        self.attention_head_count = \
            config.get('prooftrace_transformer_attention_head_count')

        self.transformer_layer_count = \
            config.get('prooftrace_transformer_layer_count')
        self.transformer_hidden_size = \
            config.get('prooftrace_transformer_hidden_size')
        self.lstm_layer_count = \
            config.get('prooftrace_transformer_layer_count')
        self.lstm_hidden_size = \
            config.get('prooftrace_lstm_hidden_size')

        self.position_embedding = nn.Embedding(
            self.sequence_length, 2*self.hidden_size
        )

        torso = [
            nn.Linear(2*self.hidden_size, self.transformer_hidden_size),
        ]

        for _ in range(self.transformer_layer_count):
            torso += [
                TransformerBlock(
                    self.sequence_length,
                    self.transformer_hidden_size,
                    self.attention_head_count,
                    dropout=0.0,
                ),
            ]

        torso += [
            nn.Linear(self.transformer_hidden_size, self.lstm_hidden_size),
        ]
        self.torso = nn.Sequential(*torso)

        if self.lstm_layer_count > 0:
            self.lstm = nn.LSTM(
                self.lstm_hidden_size, self.lstm_hidden_size,
                num_layers=self.lstm_layer_count, batch_first=True,
            )

    def parameters_count(
            self,
    ):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def forward(
            self,
            action_embeds,
            argument_embeds,
    ):
        pos_embeds = torch.arange(
            self.sequence_length, dtype=torch.long
        ).to(self.device)
        pos_embeds = pos_embeds.unsqueeze(0).expand(
           action_embeds.size(0), self.sequence_length,
        )
        pos_embeds = self.position_embedding(pos_embeds)

        embeds = torch.cat([action_embeds, argument_embeds], dim=2)
        hiddens = self.torso(embeds + pos_embeds)
        if self.lstm_layer_count > 0:
            hiddens, _ = self.lstm(hiddens)

        return hiddens
