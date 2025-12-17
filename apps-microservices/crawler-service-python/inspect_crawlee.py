import inspect
from crawlee.storages import RequestQueue
from crawlee.storages import Dataset

print("RequestQueue.open signature:")
try:
    print(inspect.signature(RequestQueue.open))
except Exception as e:
    print(e)

print("\nDataset.open signature:")
try:
    print(inspect.signature(Dataset.open))
except Exception as e:
    print(e)
