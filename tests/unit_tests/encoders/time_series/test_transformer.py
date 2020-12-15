import copy
import logging
import torch
import unittest

from lightwood.helpers.device import get_devices
from lightwood.encoders.time_series import TimeSeriesEncoder
from lightwood.encoders.time_series.helpers.transformer_helpers import TransformerEncoder, len_to_mask, get_chunk


class TestTransformerEncoder(unittest.TestCase):
    def test_get_chunk(self):
        # dimensions: (batch_size, sequence_length, feature_dimension)
        start, step = 0, 2
        batch_size, seq_len, feat_dim = 10, 5, 2

        input_tensor = torch.rand(batch_size, seq_len, feat_dim)
        len_tensor = torch.zeros(batch_size).fill_(seq_len)
        data, target, lengths = get_chunk(input_tensor, len_tensor, start, step)

        # check length vector is correct
        assert lengths.shape[0] == batch_size
        assert lengths.numpy()[0] == seq_len-1

        # check data and target
        chunk_size = min(start + step, batch_size) - start
        assert data.shape == (batch_size, chunk_size, feat_dim)
        assert target.shape == (batch_size, chunk_size, feat_dim)
        assert torch.equal(data[:, 1, :], target[:, 0, :])

        # check edge case: correct cutoff at end of sequence
        start, step = 2, 4
        chunk_size = min(start + step, seq_len) - start - 1  # -1 because of cut off
        data, target, lengths = get_chunk(input_tensor, len_tensor, start, step)
        assert data.shape == (batch_size, chunk_size, feat_dim)
        assert target.shape == (batch_size, chunk_size, feat_dim)

    def test_mask(self):
        series = [1, 3, 2, 4]
        target = [
            [True, False, False, False],
            [True, True, True, False],
            [True, True, False, False],
            [True, True, True, True],
        ]

        target = torch.tensor(target, dtype=torch.bool)
        series = torch.tensor(series)
        result = len_to_mask(series, zeros=False).t()
        self.assertTrue((result == target).all())
        target = ~target
        result = len_to_mask(series, zeros=True).t()
        self.assertTrue((result == target).all())

    def test_overfit(self):
        logging.basicConfig(level=logging.DEBUG)
        params = {"encoded_vector_size": 16, "train_iters": 10, "learning_rate": 0.001,
                  "encoder_class": TransformerEncoder}

        # Test sequences of different length
        # We just test the nothrow condition, as the control flow for BPTT and the normal one is the same
        # and the flow is tested in the next test
        data = [[1, 2, 3, 4, 5], [2, 3, 4], [3, 4, 5, 6]]
        encoder = TimeSeriesEncoder(**params)
        encoder.prepare_encoder(data, feedback_hoop_function=print)

        # Test TBPTT. Training on this woudld require a better tuning of the lr and maybe a scheduler
        # Again, just test nothrow
        data = [
            torch.rand(torch.randint(low=5, high=120, size=(1,)).item()).tolist()
            for _ in range(87)
        ]
        encoder = TransformerEncoder(**params)
        encoder.prepare_encoder(data, feedback_hoop_function=print)

        # Test Overfit
        data = [[1, 2, 3, 4, 5, 6, 7], [2, 3, 4, 5, 6, 7, 8], [3, 4, 5, 6, 7, 8, 9]]
        example = copy.deepcopy(data)
        params["train_iters"] = 1000
        encoder = TransformerEncoder(**params)
        encoder.prepare_encoder(data, feedback_hoop_function=print)

        # Test data
        example = torch.tensor(example)
        correct_answer = example[:, 1:]
        # Decoder overfit, discard last element as it doesn't correspond to answer
        answer = torch.tensor(encoder.encode(example))[:, :-1]
        # Round answer
        answer = answer.round()
        n = correct_answer.numel()
        correct = (correct_answer == answer).sum()
        print(
            "Decoder got {equal} correct and {unequal} incorrect".format(
                equal=correct, unequal=n - correct
            )
        )
        self.assertGreaterEqual(correct * 2, n - correct)
