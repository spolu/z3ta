import datetime
import os
import random
import re
import shutil
import torch
import torch.nn as nn
import typing
import time

from utils.log import Log


class IOTABase():
    def __init__(
            self,
            sync_dir: str,
            modules: typing.Dict[str, nn.Module],
    ):
        self._sync_dir = os.path.expanduser(sync_dir)
        self._tmp_dir = os.path.join(self._sync_dir, '_tmp')

        self._modules = modules

        assert os.path.isdir(self._sync_dir)

    def module(
            self,
    ):
        return self._module

    def atomic_save(
            self,
            obj,
            name: str,
    ):
        tmp_path = os.path.join(self._tmp_dir, name)
        fnl_path = os.path.join(self._sync_dir, name)

        assert not os.path.exists(fnl_path)

        torch.save(obj, tmp_path)
        os.rename(tmp_path, fnl_path)

        return fnl_path

    def list_files(
            self,
    ) -> typing.List[str]:
        return [
            os.path.join(self._sync_dir, f)
            for f in os.listdir(self._sync_dir)
            if os.path.isfile(os.path.join(self._sync_dir, f))
        ]

    def modules(
            self,
    ) -> typing.Dict[str, nn.Module]:
        return self._modules


class IOTASyn(IOTABase):
    def __init__(
            self,
            sync_dir: str,
            modules: typing.Dict[str, nn.Module],
    ):
        super(IOTASyn, self).__init__(sync_dir, modules)

        if os.path.isdir(self._tmp_dir):
            shutil.rmtree(self._tmp_dir)
        os.mkdir(self._tmp_dir)

    def broadcast(
            self,
            info: typing.Dict[str, typing.Any],
    ) -> None:
        data = {}

        for m in self._modules:
            key = "state_dict_{}".format(m)
            data[key] = self._modules[m].state_dict()
        data['info'] = info

        now = datetime.datetime.now().strftime("%Y%m%d_%H%M_%S.%f")
        rnd = random.randint(0, 10e9)
        p = self.atomic_save(data, "broadcast_{}_{}".format(now, rnd))
        Log.out("{IOTA} BROADCAST[NEW]", {'path': p})

        files = self.list_files()
        gc = sorted([
            p for p in files if re.search(".*broadcast_.*", p)
        ], reverse=True)
        if len(gc) > 2:
            for p in gc[2:]:
                assert not re.search(now, p)
                os.remove(p)
                # Log.out("{IOTA} BROADCAST[GC]", {'path': p})

    def aggregate(
            self,
            device: torch.device,
            min_update_count: int = 1,
    ) -> typing.List[
        typing.Dict[str, typing.Any]
    ]:
        files = self.list_files()
        updates = [p for p in files if re.search(".*update_.*", p)]

        infos = []

        if len(updates) < min_update_count:
            return infos

        for p in updates:
            data = torch.load(p, map_location=device)

            for m in self._modules:
                for name, param in self._modules[m].named_parameters():
                    key = "grad_{}_{}".format(m, name)
                    assert key in data
                    if param.grad is None:
                        param.grad = data[key] / len(updates)
                    else:
                        param.grad += data[key] / len(updates)

            infos.append(data['info'])

            os.remove(p)
            # Log.out("{IOTA} UPDATE[CONSUME]", {'path': p})

        return infos


class IOTAAck(IOTABase):
    def __init__(
            self,
            sync_dir: str,
            modules: typing.Dict[str, nn.Module],
    ):
        super(IOTAAck, self).__init__(sync_dir, modules)

        assert os.path.isdir(self._tmp_dir)

        self._last_broadcast = None

    def fetch(
            self,
            device: torch.device,
            blocking: bool = True,
    ) -> typing.Dict[str, typing.Any]:
        info = None
        done = False

        while not done:
            files = self.list_files()
            broadcasts = sorted([
                p for p in files if re.search(".*broadcast_.*", p)
            ], reverse=True)

            if len(broadcasts) > 0 and self._last_broadcast != broadcasts[0]:
                done = True
                self._last_broadcast = broadcasts[0]

                data = torch.load(
                    self._last_broadcast, map_location=device,
                )

                for m in self._modules:
                    key = "state_dict_{}".format(m)
                    assert key in data
                    self._modules[m].load_state_dict(data[key])
                info = data['info']

                Log.out("{IOTA} FETCH", {'path': self._last_broadcast})
            else:
                if not blocking:
                    done = True
                else:
                    time.sleep(1)

        return info

    def push(
            self,
            info: typing.Dict[str, typing.Any],
            hook: typing.Callable[
                [str, str, torch.Tensor], torch.Tensor
            ] = None,
    ) -> None:
        data = {}
        for m in self._modules:
            for name, param in self._modules[m].named_parameters():
                key = "grad_{}_{}".format(m, name)
                if hook is not None:
                    data[key] = hook(m, name, param.grad.data)
                else:
                    data[key] = param.grad.data
        data['info'] = info

        now = datetime.datetime.now().strftime("%Y%m%d_%H%M_%S.%f")
        rnd = random.randint(0, 10e9)
        p = self.atomic_save(data, "update_{}_{}".format(now, rnd))

        Log.out("{IOTA} UPDATE[NEW]", {'path': p})
