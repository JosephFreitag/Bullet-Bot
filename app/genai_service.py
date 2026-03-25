import os
import sys
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

_CONTEXT_EXTENSIONS = (".txt", ".md", ".markdown")


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
        self._active_context_name: str | None = None

        self.refresh_context_list()

    @staticmethod
    def _resolve_context_path(context_root: str | None) -> str:
        """Pick the first existing context directory (env override, PyInstaller, entry script, package, cwd)."""
        pkg_parent = Path(__file__).resolve().parent.parent
        default_missing = str(pkg_parent / "context")

        candidates: list[str] = []
        env_ctx = (os.environ.get("BULLET_BOT_CONTEXT") or os.environ.get("BULLET_BOT_CONTEXT_DIR") or "").strip()
        if env_ctx:
            candidates.append(os.path.abspath(env_ctx))
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
            self._active_context_name = None
            return

        all_names = os.listdir(self.context_path)
        found = sorted(f for f in all_names if f.lower().endswith(_CONTEXT_EXTENSIONS))
        skipped = [f for f in all_names if f not in found and not f.startswith(".")]
        for file in found:
            display_name = Path(file).stem
            self.context_files[display_name] = os.path.join(self.context_path, file)

        msg = (
            f"Context: using folder {self.context_path!r} "
            f"({len(self.context_files)} file(s): {', '.join(self.context_files.keys()) or 'none'})"
        )
        if skipped:
            msg += f" | skipped non-text: {', '.join(skipped[:12])}"
            if len(skipped) > 12:
                msg += "…"
        print(msg)
        self._debug_log(msg)

        # Default startup prompt logic
        if "EPB" in self.context_files:
            self.set_system_prompt("EPB")
        elif self.context_files:
            self.set_system_prompt(list(self.context_files.keys())[0])
        else:
            self.system_prompt = "You are a helpful assistant."
            self._active_context_name = None

    @staticmethod
    def _read_context_file(filepath: str) -> str:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return f.read()

    def _debug_log(self, line: str):
        path = os.environ.get("BULLET_BOT_DEBUG_LOG")
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def set_system_prompt(self, context_name: str | None):
        """Loads the base system prompt from the selected file."""
        if not context_name:
            self.system_prompt = "You are a helpful assistant."
            self._active_context_name = None
            return
        filepath = self.context_files.get(context_name)
        if filepath and os.path.exists(filepath):
            try:
                self.system_prompt = self._read_context_file(filepath)
                self._active_context_name = context_name
                preview = self.system_prompt[:120].replace("\n", " ")
                line = (
                    f"Loaded context {context_name!r} ({len(self.system_prompt)} chars) "
                    f"from {filepath!r} preview: {preview!r}..."
                )
                print(line)
                self._debug_log(line)
            except Exception as e:
                print(f"Error reading context file: {e}")
                self.system_prompt = "You are a helpful assistant."
                self._active_context_name = None
        else:
            print(f"Warning: Context {context_name} not found. Using default.")
            self.system_prompt = "You are a helpful assistant."
            self._active_context_name = None

    def _reload_active_context_from_disk(self):
        """Re-read the selected context file so edits apply without restarting."""
        if not self._active_context_name:
            return
        filepath = self.context_files.get(self._active_context_name)
        if filepath and os.path.exists(filepath):
            try:
                self.system_prompt = self._read_context_file(filepath)
            except Exception as e:
                print(f"Error re-reading context file: {e}")

    def get_context_status(self) -> dict:
        """Snapshot for UI: whether files load and how large the active prompt is."""
        names = sorted(self.context_files.keys())
        n_chars = len((self.system_prompt or "").strip())
        return {
            "context_path": self.context_path,
            "path_exists": os.path.isdir(self.context_path),
            "file_count": len(self.context_files),
            "names": names,
            "active": self._active_context_name,
            "prompt_chars": n_chars,
            "using_default_prompt": self._active_context_name is None or n_chars == 0,
        }

    def get_ai_response(self, user_input, history=None):
        if history is None:
            history = []

        self._reload_active_context_from_disk()

        # --- Combine base prompt with supplemental rules from the drawer ---
        full_system_instructions = (self.system_prompt or "").strip()
        if not full_system_instructions:
            full_system_instructions = "You are a helpful assistant."
        if self.supplemental_context.strip():
            full_system_instructions += (
                f"\n\nADDITIONAL USER RULES/CONTEXT:\n{self.supplemental_context.strip()}"
            )

        # Repeat instructions in the final user turn so they survive providers that ignore
        # role=system, long histories that truncate from the start, or odd OpenAI-compat gateways.
        final_user_content = (
            "Follow ALL instructions below for your reply. They override any generic assistant behavior.\n\n"
            "--- INSTRUCTIONS ---\n"
            f"{full_system_instructions}\n"
            "--- END INSTRUCTIONS ---\n\n"
            "--- USER MESSAGE ---\n"
            f"{user_input}"
        )

        messages = [{"role": "system", "content": full_system_instructions}]
        messages.extend(history)
        messages.append({"role": "user", "content": final_user_content})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model, 
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"\nAPI Error: {e}")
            return f"Sorry, I encountered an error: {e}"
