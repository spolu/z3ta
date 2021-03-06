import argparse
import eventlet
import eventlet.wsgi
import gzip
import os
import pickle
import re

from flask import Flask
from flask import render_template, jsonify

from eventlet.green import threading

from utils.config import Config
from utils.log import Log
from utils.str2bool import str2bool

_app = Flask(__name__)

_config = None

_dump = None
_traces = {}


@_app.route('/prooftrace_embeds')
def prooftrace_embeds():
    global _dump

    return render_template(
        'prooftrace_embeds.html',
        dump=_dump,
    )


@_app.route('/prooftrace_embeds/traces/<trace>')
def trace(trace):
    return jsonify(_traces[trace])


def run_server():
    global _app

    Log.out(
        "Starting embeds viewer server", {
            'port': 5001,
        })
    address = ('0.0.0.0', 5001)
    try:
        eventlet.wsgi.server(eventlet.listen(address), _app)
    except KeyboardInterrupt:
        Log.out(
            "Stopping viewer server", {})


def run():
    global _config
    global _dump
    global _traces

    parser = argparse.ArgumentParser(description="")

    parser.add_argument(
        'config_path',
        type=str, help="path to the config file",
    )
    parser.add_argument(
        '--dataset_size',
        type=str, help="config override",
    )
    parser.add_argument(
        '--test',
        type=str2bool, help="confg override",
    )

    args = parser.parse_args()

    _config = Config.from_file(args.config_path)

    if args.dataset_size is not None:
        _config.override(
            'prooftrace_dataset_size',
            args.dataset_size,
        )

    if args.test:
        dataset_dir = os.path.join(
            os.path.expanduser(_config.get('prooftrace_dataset_dir')),
            _config.get('prooftrace_dataset_size'),
            "test_traces",
        )
    else:
        dataset_dir = os.path.join(
            os.path.expanduser(_config.get('prooftrace_dataset_dir')),
            _config.get('prooftrace_dataset_size'),
            "train_traces",
        )

    ptre_path = os.path.join(dataset_dir, 'traces.embeds')
    Log.out("Loading ProofTraceEmbeds", {
        'path': ptre_path,
    })
    with gzip.open(ptre_path, 'rb') as f:
        embeds = pickle.load(f)
        _dump = {
            'embeds': dict(embeds),
        }

    files = [os.path.join(dataset_dir, f) for f in os.listdir(dataset_dir)]
    for p in files:
        if re.search("\\.actions$", p) is None:
            continue
        Log.out("Loading ProofTraceActions", {
            'path': p,
        })
        with gzip.open(p, 'rb') as f:
            ptra = pickle.load(f)
            _traces[ptra.name()] = {'actions': []}
            for i in range(ptra.len()):
                action = dict(ptra.actions()[i])
                argument = dict(ptra.arguments()[i])

                if 'hyp' in argument:
                    action['hyp'] = argument['hyp']
                    action['ccl'] = argument['ccl']
                action['hash'] = argument['hash']

                _traces[ptra.name()]['actions'].append(action)

    t = threading.Thread(target=run_server)
    t.start()
    t.join()
