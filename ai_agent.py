import logging
import os
from http.client import responses
from typing import List, Dict, Any
from tool import Tool
from tools.download_video import _download_video, _split_video_into_frames

from anthropic import Anthropic


class AIAgent:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.messages: List[Dict[str, any]] = []
        self.tools: List[Tool] = []
        self._setup_tools()
        print(f'Agent setup init with {len(self.tools)}')

    def _setup_tools(self):
        self.tools = [
            Tool(
                name="read_file",
                description="Read the content of a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The part to the file to read",
                        }
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="list_file",
                description="List a files in a directory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The directory path of the list (default to current directory",
                        }
                    },
                    "required": [],
                },
            ),
            Tool(
                name="edit_file",
                description="Edit a file by replacing old_text with new_text. creates the file if it does not exist",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "path to the file to edit",
                        },
                        "old_text": {
                            "type": "string",
                            "description": "The text to search for and replace (leave empty to create new file)",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "The text to replace old_text with",
                        }
                    },
                    "required": [],
                },
            ),
            Tool(
                name="download_video",
                description="Download a video from a direct http(s) video URL and save it to a local folder",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Direct URL of the video file (e.g. https://example.com/clip.mp4)",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Folder to save the video in (defaults to 'downloads')",
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional file name to save the video as",
                        },
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="split_video_into_frames",
                description="Split a local video file into image frames and save them to a folder",
                input_schema={
                    "type": "object",
                    "properties": {
                        "video_path": {
                            "type": "string",
                            "description": "Path to the local video file",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Folder to save frames in (defaults to '<video name>_frames' next to the video)",
                        },
                        "every_n_frames": {
                            "type": "integer",
                            "description": "Save one frame out of every N frames (default 1 = every frame)",
                        },
                        "image_format": {
                            "type": "string",
                            "description": "Image format for the frames: jpg or png (default jpg)",
                        },
                        "max_frames": {
                            "type": "integer",
                            "description": "Maximum number of frames to save (default 0 = no limit)",
                        },
                    },
                    "required": ["video_path"],
                },
            ),

        ]

    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        try:
            if tool_name == 'read_file':
                return self._read_file(tool_input['path'])
            elif tool_name == 'edit_file':
                return self._edit_file(
                    path=tool_input['path'],
                    old_text=tool_input.get('old_text', ''),
                    new_text=tool_input['new_text'],
                )
            elif tool_name == 'list_file':
                return self._list_files(
                    path=tool_input.get('path', '')
                )
            elif tool_name == 'download_video':
                return _download_video(
                    url=tool_input['url'],
                    output_dir=tool_input.get('output_dir') or 'downloads',
                    filename=tool_input.get('filename', ''),
                )
            elif tool_name == 'split_video_into_frames':
                return _split_video_into_frames(
                    video_path=tool_input['video_path'],
                    output_dir=tool_input.get('output_dir', ''),
                    every_n_frames=tool_input.get('every_n_frames', 1),
                    image_format=tool_input.get('image_format', 'jpg'),
                    max_frames=tool_input.get('max_frames', 0),
                )
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _read_file(self, path: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                return f"File content of {path}:\n{content}"
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def _list_files(self, path: str) -> str:
        try:
            if not os.path.exists(path):
                return f"Path not found; {path}"

            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    items.append(f"[Dire] {item}")
                else:
                    items.append(f'[File] {item}')

            if not items:
                return f"Empty directory: {path}"

            return f"Contents of {path}:\n" + "\n".join(items)
        except Exception as e:
            return f"Error listing files: {str(e)}"

    def _edit_file(self, path: str, old_text: str, new_text: str) -> str:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if old_text not in content:
                        return f"text not found in file:{old_text}"
                    content = content.replace(old_text, new_text)

                    with open(path, 'w', encoding='utf-8') as w:
                        w.write(content)
                return f"Successfully edited {path}"
            else:
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_text)
                return f"Successfully created {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    def chat(self, user_input: str):
        logging.info(f"User input: {user_input}")
        self.messages.append({"role": "user", "content": user_input})
        tool_schemas = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in self.tools
        ]

        while True:
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-5-5",
                    max_tokens=4096,
                    messages=self.messages,
                    tools=tool_schemas,
                    system="You are a helpful coding assistant operating in a terminal environment. Output only plain text without markdown formatting, as your responses appear directly in the terminal. Be concise but thorough, providing clear and practical advice with a friendly tone. Don't use any asterisk characters in your responses.",
                )
                assistant_message = {
                    'role': "assistant",
                    'content': []
                }
                self.messages.append({
                    "role": "assistant",
                    "content": [
                        block.model_dump() for block in response.content
                    ],
                })
                self.messages.append(assistant_message)
                tool_results = []
                for content in response.content:
                    if content.type == "tool_use":
                        result = self._execute_tool(content.name, content.input)
                        logging.info(
                            f"Tool result: {result[:500]}..."
                        )  # Log first 500 chars
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result,
                            }
                        )

                if tool_results:
                    self.messages.append({"role": "user", "content": tool_results})
                else:
                    return "\n".join(
                        block.text
                        for block in response.content
                        if block.type == "text"
                    )


            except Exception as e:
                logging.exception("Agent API error")
                return f"Error from our agent: {e}"
