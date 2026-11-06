"""Execute the notebooks and verify each owned temporary kernel exits."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import nbformat
from nbclient import NotebookClient
import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/notebooks'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    args.output.mkdir(parents=True, exist_ok=True)
    resources = []
    for path in sorted((root/'notebooks').glob('*.ipynb')):
        notebook = nbformat.read(path, as_version=4)
        client = NotebookClient(notebook, timeout=90, kernel_name='python3', resources={'metadata':{'path':str(root)}})
        owned = {}

        def record_kernel(**kwargs):
            process = psutil.Process(client.km.provisioner.pid)
            connection = client.km.get_connection_info()
            owned.update(owner=str(path.relative_to(root)), pid=process.pid,
                         started_utc=datetime.fromtimestamp(process.create_time(),timezone.utc).isoformat(),
                         create_time=process.create_time(),
                         ports={k:v for k,v in connection.items() if k.endswith('_port')},
                         cleanup=f'NotebookClient context shutdown; emergency: verify start time then kill -TERM {process.pid}')
            # Never print the kernel connection key.
            print('Owned notebook kernel: '+json.dumps(owned,sort_keys=True), flush=True)

        client.on_notebook_start = record_kernel
        try:
            # NotebookClient owns its manager and shuts down in a finally block,
            # including cell failure and interruption paths.
            client.execute()
            nbformat.write(notebook, args.output/path.name)
            print(f'Executed {path.name}')
        finally:
            if owned:
                try:
                    process = psutil.Process(owned['pid'])
                    alive = process.create_time() == owned['create_time'] and process.is_running()
                except psutil.NoSuchProcess:
                    alive = False
                owned['cleanup_verified'] = not alive
                resources.append(owned)
                (args.output/'kernel-resources.json').write_text(json.dumps(resources,indent=2)+'\n')
                if alive:
                    raise RuntimeError(f'Owned notebook kernel {owned["pid"]} still exists after context shutdown')


if __name__ == '__main__':
    main()
