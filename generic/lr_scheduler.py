import math

from torch.optim.lr_scheduler import _LRScheduler


class LRScheduler(_LRScheduler):
    """ LRScheduler ramps up the learning rate from `lr_min` to the `base_lr`
    over `ramp_up` epochs and then apply cosine annealing between `lr_min` and
    `base_lr` with period `period`.
    """
    def __init__(self, optimizer, ramp_up, period, lr_min):
        self._period = period
        self._ramp_up = ramp_up
        self._lr_min = lr_min
        super(LRScheduler, self).__init__(optimizer, -1)

    def get_lr(self):
        if self.last_epoch < self._ramp_up:
            alpha = self.last_epoch / self._ramp_up
            return [
                (1 - alpha) * self._lr_min + alpha * base_lr
                for base_lr in self.base_lrs
            ]
        else:
            return [
                self._lr_min + (base_lr - self._lr_min) *
                (1 + math.cos(
                    math.pi * (self.last_epoch - self._ramp_up) / self._period
                )) / 2
                for base_lr in self.base_lrs]
