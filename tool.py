from typing import Dict, Any

from pydantic import BaseModel


class Tool(BaseModel):
      name:str
      description:str
      input_schema:Dict[str,Any]
