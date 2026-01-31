# This module contains the class reponsible for reading the configuration files and
# loading them in a data structure

import json
import os

class ConfigLoader:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance

    def __init__(self, filenames=None, variables=None):
        # Ensure the data is only loaded once
        if self._initialized:
            return
        
        self.config_data = {}
        if filenames and variables:
            self.load_files(filenames)
            self.load_environment_variables(variables)
            self._initialized = True

    def load_files(self, filenames):
        if isinstance(filenames, str):
            filenames = [filenames]
            
        for filename in filenames:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    # Assuming JSON for this example
                    data = json.load(f)
                    self.config_data.update(data)
            else:
                print(f"Warning: Configuration file {filename} not found.")

    def load_environment_variables(self, variables):
        if isinstance(variables, str):
            variables = [variables]
        
        for var_name in variables:
            if var_name in os.environ:
                self.config_data[var_name] = os.environ[var_name]

    def get(self, key, default=None):
        return self.config_data.get(key, default)