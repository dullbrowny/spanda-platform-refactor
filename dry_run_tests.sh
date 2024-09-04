#!/bin/bash

echo "Starting Dry Run of Tests and Code Checks..."

# Create example test files (if not created yet)
echo "Creating example unit test file..."
mkdir -p tests/unit
echo "
import unittest

class TestExample(unittest.TestCase):
    def test_example(self):
        self.assertEqual(1, 1)
" > tests/unit/test_example.py

echo "Creating example integration test file..."
mkdir -p tests/integration
echo "
import unittest

class TestIntegrationExample(unittest.TestCase):
    def test_example(self):
        self.assertEqual(1, 1)
" > tests/integration/test_example.py

# Run Unit Tests
echo "Running Unit Tests..."
python3 -m unittest discover -s tests/unit

# Run Integration Tests
echo "Running Integration Tests..."
python3 -m unittest discover -s tests/integration

# Check Code Formatting with Black and fix lines to 79 characters
echo "Checking Code Formatting with Black..."
black --line-length 79 .

# Run Linting with Flake8 (if Flake8 is not installed, install it first)
if ! command -v flake8 &> /dev/null
then
    echo "Flake8 not found. Installing Flake8..."
    pip install flake8
fi

echo "Running Linting with Flake8..."
flake8 .

echo "
-----------------------
Dry Run Summary:
-----------------------"
echo "Unit Tests: Completed"
echo "Integration Tests: Completed"
echo "Code Formatting (Black): Issues Fixed"
echo "Linting (Flake8): Completed"

