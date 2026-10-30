# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ashish Sinha.
"""Entry point target (``nat_schemagate``): importing it runs the registration decorators."""

from . import functions
from . import retriever

__all__ = ["functions", "retriever"]
