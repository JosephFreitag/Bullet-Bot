import os
import sys
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class GenAIService:
    # 1. REMOVE the context_dir parameter from the signature
    def __init__(self, model="gemini-2.5-pro-latest"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        self.model = model
        
        if not self.api_key or "YOUR_ACTUAL_API_KEY_HERE" in self.api_key:
            raise ValueError("API key not found. Please check your .env file.")
            
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        # 2. REPLACE the old if/else block with this unified logic
        # This single block correctly finds the path for both dev and PyInstaller
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            # If not packaged, use the normal script path
            base_path = os.path.abspath(".")
        
        self.context_path = os.path.join(base_path, "context")
        
        self.context_files = {}
        self.system_prompt = ""
        self.supplemental_context = "" 
        
        self.refresh_context_list()

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
            if file.endswith(".txt"):
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

    def set_system_prompt(self, context_name: str):
        """Loads the base system prompt from the selected file."""
        filepath = self.context_files.get(context_name)
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
            except Exception as e:
                print(f"Error reading context file: {e}")
        else:
            print(f"Warning: Context {context_name} not found. Using default.")

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
