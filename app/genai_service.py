import os
import sys
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

from app.multimodal import (
    PendingAttachment,
    build_latest_user_content,
    history_content_for_api,
)

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

        for file in sorted(
            f for f in os.listdir(self.context_path) if f.lower().endswith(_CONTEXT_EXTENSIONS)
        ):
            display_name = Path(file).stem
            self.context_files[display_name] = os.path.join(self.context_path, file)

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

    @staticmethod
    def _normalize_history_for_api(history: list[dict] | None) -> list[dict[str, Any]]:
        if not history:
            return []
        out: list[dict[str, Any]] = []
        for m in history:
            if m.get("role") == "user":
                raw = m.get("content", "")
                out.append({"role": "user", "content": history_content_for_api(raw)})
            else:
                out.append({"role": m["role"], "content": m.get("content", "")})
        return out

    def instruction_prefix(self) -> str:
        full_system_instructions = (self.system_prompt or "").strip()
        if not full_system_instructions:
            full_system_instructions = "You are a helpful assistant."
        if self.supplemental_context.strip():
            full_system_instructions += (
                f"\n\nADDITIONAL USER RULES/CONTEXT:\n{self.supplemental_context.strip()}"
            )
        return (
            "Follow ALL instructions below for your reply. They override any generic assistant behavior.\n\n"
            "--- INSTRUCTIONS ---\n"
            f"{full_system_instructions}\n"
            "--- END INSTRUCTIONS ---\n\n"
            "--- USER MESSAGE ---\n"
        )

    def _build_chat_messages(
        self,
        user_input: str,
        history=None,
        attachments: list[PendingAttachment] | None = None,
    ):
        history = history or []
        attachments = attachments or []

        self._reload_active_context_from_disk()

        full_system_instructions = (self.system_prompt or "").strip()
        if not full_system_instructions:
            full_system_instructions = "You are a helpful assistant."
        if self.supplemental_context.strip():
            full_system_instructions += (
                f"\n\nADDITIONAL USER RULES/CONTEXT:\n{self.supplemental_context.strip()}"
            )

        prefix = self.instruction_prefix()
        last_content, err = build_latest_user_content(prefix, user_input, attachments)
        if err:
            raise ValueError(err)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": full_system_instructions}
        ]
        messages.extend(self._normalize_history_for_api(history))
        messages.append({"role": "user", "content": last_content})
        return messages

    def estimate_prompt_tokens(
        self, user_input, history=None, attachments: list[PendingAttachment] | None = None
    ) -> int:
        """Rough token count for billing fallback (~4 chars per token)."""
        try:
            messages = self._build_chat_messages(user_input, history, attachments)
        except ValueError:
            messages = self._build_chat_messages("", history, [])
        chars = 0
        for m in messages:
            c = m.get("content")
            if isinstance(c, str):
                chars += len(c)
            elif isinstance(c, list):
                for p in c:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") == "text":
                        chars += len(p.get("text") or "")
                    else:
                        chars += 8000
        return max(1, chars // 4)

    @staticmethod
    def _usage_dict_from_api(usage_obj) -> dict | None:
        if usage_obj is None:
            return None
        total = getattr(usage_obj, "total_tokens", None)
        prompt = getattr(usage_obj, "prompt_tokens", None)
        completion = getattr(usage_obj, "completion_tokens", None)
        if total is None and prompt is None and completion is None:
            return None
        pt = int(prompt or 0)
        ct = int(completion or 0)
        tot = int(total) if total is not None else pt + ct
        return {"total_tokens": tot, "prompt_tokens": pt, "completion_tokens": ct}

    def get_ai_response(
        self, user_input, history=None, attachments: list[PendingAttachment] | None = None
    ):
        messages = self._build_chat_messages(user_input, history, attachments)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content, self._usage_dict_from_api(
                getattr(response, "usage", None)
            )
        except Exception as e:
            print(f"\nAPI Error: {e}")
            return f"Sorry, I encountered an error: {e}", None

    def stream_ai_response(
        self,
        user_input,
        history=None,
        usage_out: list | None = None,
        attachments: list[PendingAttachment] | None = None,
    ):
        """Yields text fragments; optional usage_out list receives one usage dict if the API reports it."""
        try:
            messages = self._build_chat_messages(user_input, history, attachments)
        except ValueError as e:
            yield str(e)
            return

        last_usage = None
        try:
            try:
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                )
            except Exception:
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                )
            for chunk in stream:
                u = getattr(chunk, "usage", None)
                parsed = self._usage_dict_from_api(u)
                if parsed:
                    last_usage = parsed
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            print(f"\nAPI Error: {e}")
            yield f"Sorry, I encountered an error: {e}"
        finally:
            if usage_out is not None and last_usage is not None:
                usage_out.append(last_usage)

    def validate_user_turn(
        self, user_input: str, history=None, attachments: list[PendingAttachment] | None = None
    ) -> str | None:
        """Return error string if the turn cannot be built, else None."""
        try:
            self._build_chat_messages(user_input, history, attachments)
        except ValueError as e:
            return str(e)
        return None
