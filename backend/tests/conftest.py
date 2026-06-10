import os

# Force the TESTING environment variable so that database.py
# always routes connection to second_brain_test instead of second_brain.
os.environ["TESTING"] = "1"
