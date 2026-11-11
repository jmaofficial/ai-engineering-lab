
class ToolRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, name, func):
        self._registry[name] = func

    def get(self, name):
        if name not in self._registry:
            raise ValueError(f"Tool '{name}' is not registered.")
        return self._registry[name]

    def get_all(self):
        return self._registry