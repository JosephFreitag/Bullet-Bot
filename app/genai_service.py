import os
import sys
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

_CONTEXT_EXTENSIONS = (".txt", ".md")


class GenAIService:
    def __init__(self, model="gemini-2.5-pro-latest", context_root: str | None = None):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        self.model = model
        
        if not self.api_key or "YOUR_ACTUAL_API_KEY_HERE" in self.api_key:
            raise ValueError("API key not found. Please check your .env file.")
            
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        self.context_path = self._resolve_context_path(context_root)
        
        self.context_files = {}
        self.system_prompt = ""
        self.supplemental_context = "" 
        
        self.refresh_context_list()

    @staticmethod
    def _resolve_context_path(context_root: str | None) -> str:
        """Pick the first existing context/ directory (PyInstaller, entry script dir, package root, cwd)."""
        pkg_parent = Path(__file__).resolve().parent.parent
        default_missing = str(pkg_parent / "context")

        candidates: list[str] = []
        try:
            candidates.append(os.path.join(sys._MEIPASS, "context"))
        except Exception:
            pass
        if context_root:
            candidates.append(os.path.join(os.path.abspath(context_root), "context"))
        candidates.append(default_missing)
        candidates.append(os.path.join(os.path.abspath(os.getcwd()), "context"))

        for path in candidates:
            if os.path.isdir(path):
                return path
        return default_missing

    def refresh_context_list(self):
        """Scans the context folder for all .txt files and maps them."""
        self.context_files = {}
        
        # In a read-only EXE environment (sys._MEIPASS), 
        # we should NOT try to makedirs if it doesn't exist.
        if not os.path.exists(self.context_path):
            print(f"Warning: Context path {self.context_path} does not exist.")
            self.system_prompt = "You are a helpful assistant."
            return
            
        for file in os.listdir(self.context_path):
            if file.lower().endswith(_CONTEXT_EXTENSIONS):
                display_name = Path(file).stem
                # Map the name to the FULL path of the file
                self.context_files[display_name] = os.path.join(self.context_path, file)
        
        # Default startup prompt logic
        if "EPB" in self.context_files:
            self.set_system_prompt("EPB")
        elif self.context_files:
            self.set_system_prompt(list(self.context_files.keys())[0])
        else:
            self.system_prompt = "You are a helpful assistant."

    def set_system_prompt(self, context_name: str | None):
        """Loads the base system prompt from the selected file."""
        if not context_name:
            self.system_prompt = "You are a helpful assistant."
            return
        filepath = self.context_files.get(context_name)
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
            except Exception as e:
                print(f"Error reading context file: {e}")
                self.system_prompt = "You are a helpful assistant."
        else:
            print(f"Warning: Context {context_name} not found. Using default.")
            self.system_prompt = "You are a helpful assistant."

    def get_ai_response(self, user_input, history=None):
        if history is None:
            history = []
            
        # --- Combine base prompt with supplemental rules from the drawer ---
        full_system_instructions = self.system_prompt
        if self.supplemental_context.strip():
            full_system_instructions += f"\n\nADDITIONAL USER RULES/CONTEXT:\n{self.supplemental_context}"

        messages = [{"role": "system", "content": full_system_instructions}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model, 
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"\nAPI Error: {e}")
            return f"Sorry, I encountered an error: {e}"
