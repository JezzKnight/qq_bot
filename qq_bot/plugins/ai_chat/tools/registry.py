from typing import Callable

TOOLS: dict[str, dict] = {}

def register_tool(name: str, description: str, parameters: dict):
    def decorator(func: Callable):
        TOOLS[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "func": func,
        }
        return func
    return decorator

def get_tools_schema(*args) -> list[dict]:
    if args:
        tools_list = []
        for i in TOOLS.values():
            if i["name"] in args:
                tools_list.append({
                "type": "function",
                "function": {
                    "name": i["name"],
                    "description": i["description"],
                    "parameters": i["parameters"],
                }})
            else:
                continue
        return tools_list
    else:
        return [
            {
                "type": "function",
                "function": {
                    "name": i["name"],
                    "description": i["description"],
                    "parameters": i["parameters"],
                },
            }
            for i in TOOLS.values()
        ]