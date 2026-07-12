"""Optional trainer-framework adapters. Every import is lazy."""

from rath.training.adapters.trl import to_trl_dataset
from rath.training.adapters.verl import to_verl_data_proto

__all__ = ["to_trl_dataset", "to_verl_data_proto"]
