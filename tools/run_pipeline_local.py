import sys
import json
import uuid
import time

# Ensure project root is importable
sys.path.insert(0, '.')

from app import run_pipeline, Task, TaskStatus, tasks

if __name__ == '__main__':
    task_id = str(uuid.uuid4())
    task = Task(
        task_id=task_id,
        status=TaskStatus.PENDING,
        progress=0,
        message='Local test run',
        repo_path='.'
    )
    tasks[task_id] = task

    print(f"Starting pipeline for task {task_id} (use_bob=False)")
    start = time.time()
    # Run synchronously without Bob to avoid external API
    run_pipeline(task_id, repo_path='.', use_bob=False)
    duration = time.time() - start
    print(f"Pipeline finished in {duration:.2f}s")
    print(json.dumps(tasks[task_id].to_dict(), indent=2))
