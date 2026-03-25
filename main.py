import flet as ft
import re
import asyncio
import os
import sys
from app.genai_service import GenAIService
from app.database import DatabaseService
from flet import Clipboard

# Resolve paths from the directory that contains main.py (stable when cwd differs, e.g. IDE run).
_APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# Database stays next to main.py / EXE (not inside PyInstaller temp when bundled).
db_path = os.path.join(_APP_ROOT, "bullet_bot.db")

genai_service = GenAIService(model="gemini-2.5-pro", context_root=_APP_ROOT)
db_service = DatabaseService(db_path=db_path)


async def main(page: ft.Page):
    # --- 1. Page & Application Setup ---
    page.title = "Performance Statement Writer"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1200
    page.window_height = 800
    page.padding = 10  # Simplified for 3.14 stability
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    logout_button = ft.IconButton(
        icon=ft.Icons.LOGOUT, 
        tooltip="Logout",
        visible=False,
        on_click=None # We will attach this later
    )

    # 2. Update the AppBar to use that specific variable
    page.appbar = ft.AppBar(
        title=ft.Text("Bullet Bot Login"),
        center_title=True,
        bgcolor="#2d2d2d",
        automatically_imply_leading=False,
        actions=[logout_button]
    )

        # --- 2. Application State Management ---
    current_conversation_id = None
    logged_in_user = None  # This replaces the session/storage entirely

    def get_user_from_session():
        """Retrieves the current user's data from client storage."""
        return page.client_storage.get("user")

    def set_user_in_session(user_data):
        """Saves the current user's data to client storage."""
        page.client_storage.set("user", user_data)

    # --- 3. UI Control Definitions (Moved placeholders here) ---
    # We define the controls first, then define functions, 
    # then assign the functions to the controls.
    
    login_username_field = ft.TextField(label="Username", width=300, autofocus=True)
    login_password_field = ft.TextField(label="Password", password=True, width=300)
    reg_username_field = ft.TextField(label="New Username", width=300)
    reg_password_field = ft.TextField(label="New Password", password=True, width=300)
        # --- Supplemental Drawer Controls ---
    supp_input = ft.TextField(
        label="Additional Rules / Context",
        hint_text="e.g., 'Focus on leadership' or 'Use active verbs'", # <--- Hint Text
        multiline=True,
        min_lines=10,
        max_lines=20,
        text_size=13,
        border_color="#424242",
    )

    history_list = ft.ListView(expand=True, spacing=5, padding=5)
    chat_display = ft.ListView(expand=True, spacing=10, auto_scroll=True)

    input_field = ft.TextField(
        multiline=True,
        min_lines=1,
        max_lines=5,
        expand=True,
        border=ft.InputBorder.NONE,
        filled=False,
    )
    context_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(name) for name in genai_service.context_files.keys()],
        value="EPB" if "EPB" in genai_service.context_files else 
              (list(genai_service.context_files.keys())[0] if genai_service.context_files else None),
        width=150,
        border=ft.InputBorder.NONE,
        content_padding=ft.Padding(10, 0, 0, 0),
        color="#B0B0B0",
        text_size=13,
    )

    context_status_text = ft.Text(
        "",
        size=11,
        selectable=True,
        max_lines=4,
        overflow=ft.TextOverflow.VISIBLE,
    )

    def refresh_context_status_ui():
        s = genai_service.get_context_status()
        full_path = s["context_path"]
        if s["file_count"] == 0:
            context_status_text.value = (
                f"No .txt/.md context files found. Folder: {full_path}\n"
                f"Tip: add EPB.txt (or set BULLET_BOT_CONTEXT in .env to your context folder)."
            )
            context_status_text.color = "#e57373"
        elif s["using_default_prompt"]:
            context_status_text.value = (
                f"Found {s['file_count']} file(s) {s['names']!r} but active prompt is empty/default. "
                f"Choose one in the dropdown."
            )
            context_status_text.color = "#ffb74d"
        else:
            context_status_text.value = (
                f"Loaded “{s['active']}” ({s['prompt_chars']} chars) from:\n{full_path}"
            )
            context_status_text.color = "#9e9e9e"
        context_status_text.tooltip = full_path
    
    send_button = ft.IconButton(
        icon=ft.Icons.SEND, 
        icon_color="#B0B0B0", 
        bgcolor=None, 
        tooltip="Send"
    )

    new_chat_button = ft.FilledButton(
        "＋ New Chat",
        width=300,
        style=ft.ButtonStyle(color="#B0B0B0", bgcolor="#383838")
    )

    # Create the button to trigger the drawer (Place this near your send button)
    settings_button = ft.IconButton(
        icon=ft.Icons.TUNE, 
        icon_color="#B0B0B0", 
        tooltip="Fine-Tune Rules", 
        visible=False
        # DO NOT PUT on_click HERE
    )

    async def save_supp_rules(e):
        # 1. Apply the logic to the AI service
        genai_service.supplemental_context = supp_input.value
        
        # 2. Use your exact working "toast" logic for 0.82
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text("Rules Applied!", color="white", size=12, text_align=ft.TextAlign.CENTER),
                bgcolor="#4CAF50",
                duration=1000,
                behavior=ft.SnackBarBehavior.FLOATING,
                # Using your margin trick to keep it narrow on the left
                margin=ft.Margin.only(left=10, bottom=20, right=page.window_width - 240), 
            )
        )
        
        # 3. Close the drawer if it's open
        if page.end_drawer:
            page.end_drawer.open = False
            
        # 4. Trigger the UI update
        page.update()

    my_fine_tune_drawer = ft.NavigationDrawer(
        controls=[
            ft.Container(
                padding=20,
                content=ft.Column([
                    ft.Text("Fine-Tune AI", size=20, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    supp_input,
                    ft.FilledButton("Apply to AI",
                    on_click=save_supp_rules,
                    ),
                ])
            )
        ]
    )
    # --------------------------------------------------------------------------
    # 4. Core Logic and Event Handlers
    # --------------------------------------------------------------------------


# In section "# 4. Core Logic and Event Handlers"

    def create_bot_response_view(page: ft.Page, bot_response_text: str):
        """
        Parses the bot's markdown response and builds a list of Flet controls,
        adding a copy button to each bullet point.
        """
        response_column = ft.Column(spacing=8, expand=True)

        # --- Clipboard copy handler following modern Flet docs ---
        async def copy_to_clipboard(e):
            text_to_copy = str(e.control.data) if e.control.data else ""

            # 1. Perform the copy
            await ft.Clipboard().set(text_to_copy)

            # 2. Show the SnackBar anchored left via Margin
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Copied!", color="white", size=12, text_align=ft.TextAlign.CENTER),
                    bgcolor="#4CAF50",
                    duration=1000,
                    behavior=ft.SnackBarBehavior.FLOATING,
                    # IMPORTANT: width MUST be removed for margin to work
                    # We use a massive 'right' margin to simulate a narrow width on the left
                    margin=ft.Margin.only(left=10, bottom=20, right=page.window_width - 240), 
                )
            )

        
        # --- Parse the bot response into lines ---
        lines = bot_response_text.strip().split('\n')
        
        for line in lines:
            stripped_line = line.strip()
            # Check for bullet points or numbered lists
            if stripped_line.startswith(('* ', '- ')) or (stripped_line and stripped_line[0].isdigit() and '.' in stripped_line):
                
                # Logic to clean the prefix for the clipboard
                if stripped_line.startswith('* '):
                    clean_text = stripped_line[2:]
                elif stripped_line.startswith('- '):
                    clean_text = stripped_line[2:]
                else:
                    import re # Ensure re is imported at the top of your file
                    match = re.search(r'^\d+\.\s+', stripped_line)
                    clean_text = stripped_line[match.end():] if match else stripped_line
                
                statement_row = ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Markdown(
                            line,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.COPY,
                            icon_size=16,
                            icon_color="#9E9E9E",
                            tooltip="Copy Statement",
                            data=clean_text, # This is what copy_to_clipboard reads
                            on_click=copy_to_clipboard, 
                        )
                    ]
                )
                response_column.controls.append(statement_row)
            
            elif stripped_line:
                response_column.controls.append(
                    ft.Markdown(
                        line,
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        expand=True 
                    )
                )
                
        return ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text("Bullet Bot", weight=ft.FontWeight.BOLD, color="#ff9800"),
                    alignment=ft.Alignment.TOP_LEFT,
                    width=80
                ),
                response_column,
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    async def login(e):
        nonlocal logged_in_user
        user = db_service.verify_user(login_username_field.value, login_password_field.value)
        if user:
            logged_in_user = user
            login_view.visible = False
            chat_view.visible = True
            
            # --- SHOW BUTTONS ---
            logout_button.visible = True
            settings_button.visible = True 
            
            page.appbar.title = ft.Text(f"Bullet Bot Ghost Writing For {user['username']}")
            await load_history_list()
            await START_new_chat(None)
            page.update()
        else:
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Invalid Login!", size=12, text_align=ft.TextAlign.CENTER),
                    bgcolor="#4CAF50",
                    width=100,           # Small fixed width
                    behavior=ft.SnackBarBehavior.FLOATING,
                    duration=2000,
                )
            )
            page.update()

    async def register(e):
        user_id = db_service.create_user(reg_username_field.value, reg_password_field.value)
        if user_id:
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Registration Successful!", size=12, text_align=ft.TextAlign.CENTER),
                    bgcolor="#4CAF50",
                    width=100,           # Small fixed width
                    behavior=ft.SnackBarBehavior.FLOATING,
                    duration=2000,
                )
            )
            # Clear fields so user knows it happened
            reg_username_field.value = ""
            reg_password_field.value = ""
        else:
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Username Taken!", size=12, text_align=ft.TextAlign.CENTER),
                    bgcolor="#4CAF50",
                    width=100,           # Small fixed width
                    behavior=ft.SnackBarBehavior.FLOATING,
                    duration=2000,
                )
            )
        page.update()

    async def logout_click(e):
        nonlocal logged_in_user, current_conversation_id
        logged_in_user = None
        current_conversation_id = None
        
        # --- DETACH DRAWER TO HIDE HAMBURGER ---
        page.end_drawer = None 
        
        login_view.visible = True
        chat_view.visible = False
        
        # --- HIDE BUTTONS ---
        logout_button.visible = False
        settings_button.visible = False
        
        page.appbar.title = ft.Text("Bullet Bot Login")
        page.update()
    
    logout_button.on_click = logout_click

    async def sync_context_on_change(e):
        """Updates the AI prompt immediately without clearing the chat."""
        try:
            new_context = context_dropdown.value
            # Tell the backend to load the file
            genai_service.set_system_prompt(new_context)
            refresh_context_status_ui()

            # Show visual feedback
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"AI switched to {new_context} mode"),
                bgcolor="#383838",
                duration=1500
            )
            page.snack_bar.open = True
            print(f"Successfully switched to: {new_context}")
        except Exception as ex:
            print(f"Error switching context: {ex}")
            page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red")
            page.snack_bar.open = True
        
        page.update()

    async def load_history_list():
        if not logged_in_user: return
        history_list.controls.clear()
        conversations = db_service.get_conversations(logged_in_user['id'])
        
        for conv_id, title in conversations:
            history_list.controls.append(
                ft.Container(
                    padding=5,
                    border_radius=4,
                    # We use a Row so the text and delete button sit side-by-side
                    content=ft.Row([
                        # The Title (Clicking this loads the chat)
                        ft.Container(
                            content=ft.Text(title, color="#EAEAEA", overflow=ft.TextOverflow.ELLIPSIS),
                            expand=True,
                            on_click=load_conversation_click,
                            data=conv_id,
                        ),
                        # The Delete Button
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_color="#757575",
                            icon_size=18,
                            tooltip="Delete Chat",
                            # Wrap the call in asyncio.create_task to execute the coroutine
                            on_click=lambda e, cid=conv_id: asyncio.create_task(delete_chat_click(e, cid))
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                )
            )
        page.update()

    async def START_new_chat(e):
        """Clears the chat interface and ensures the AI matches the current dropdown."""
        nonlocal current_conversation_id
        current_conversation_id = None
        
        # Make sure the service is synced to whatever the dropdown is currently showing
        genai_service.set_system_prompt(context_dropdown.value)
        refresh_context_status_ui()

        chat_display.controls.clear()
        input_field.value = ""
        for control in history_list.controls:
            control.bgcolor = None
            
        page.update()

    # Dropdown Sync
    context_dropdown.on_change = sync_context_on_change
    
    # "New Chat" button clears the chat
    new_chat_button.on_click = START_new_chat 

    async def send_message_click(e):
        nonlocal current_conversation_id

        # 1. NEW: Sync BOTH the dropdown and the supplemental text box right away
        genai_service.set_system_prompt(context_dropdown.value)
        genai_service.supplemental_context = supp_input.value # <--- Adds your manual rules
        refresh_context_status_ui()

        user_input = input_field.value.strip()
        if not logged_in_user or not user_input:
            return

        # --- UI State: Disable inputs while processing ---
        input_field.disabled = True
        send_button.disabled = True
        send_button.icon_color = "#424242" 
        input_field.value = ""
        page.update()

        # --- Display User's Message ---
        chat_display.controls.append(ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text("You", weight=ft.FontWeight.BOLD, color="#81d4fa"), 
                    alignment=ft.Alignment.TOP_LEFT,
                    width=80
                ),
                ft.Markdown(user_input, extension_set=ft.MarkdownExtensionSet.COMMON_MARK, code_theme="atom-one-dark", expand=True)
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ))

        # --- Display "Thinking..." Indicator ---
        thinking_row = ft.Row( # Renamed for clarity
            controls=[
                ft.Container(
                    content=ft.Text("Bullet Bot", weight=ft.FontWeight.BOLD, color="#ff9800"), 
                    alignment=ft.Alignment.TOP_LEFT,
                    width=80
                ),
                ft.ProgressRing(width=16, height=16, stroke_width=2)
            ],
            spacing=10,
        )
        chat_display.controls.append(thinking_row)
        page.update()

        # --- Conversation row: create if needed, then one API call with prior messages only ---
        if current_conversation_id is None:
            ctx_label = context_dropdown.value or "Default"
            title = f"[{ctx_label}] {user_input[:25]}"
            current_conversation_id = db_service.create_conversation(logged_in_user['id'], title)
            await load_history_list()

        prior_history = db_service.get_messages(current_conversation_id)

        bot_response = await asyncio.to_thread(
            genai_service.get_ai_response,
            user_input,
            prior_history,
        )

        db_service.add_message(current_conversation_id, "user", user_input)
        db_service.add_message(current_conversation_id, "assistant", bot_response)

        chat_display.controls.remove(thinking_row)

        # Generate the rich response view with copy buttons using the helper function
        bot_response_view = create_bot_response_view(page, bot_response)
        
        # Add the generated view to the chat display
        chat_display.controls.append(bot_response_view)

        # --- UI State: Re-enable inputs ---
        input_field.disabled = False
        send_button.disabled = False
        send_button.icon_color = "#B0B0B0" # Back to normal
        
        # Final update and focus
        await input_field.focus()
        page.update()


    async def load_conversation_click(e):
        """Loads a selected conversation and dynamically syncs the AI context."""
        nonlocal current_conversation_id

        # --- 1. UI & State Setup ---
        # Highlight the selected item in the sidebar
        for control in history_list.controls:
            if isinstance(control, ft.Container):
                control.bgcolor = None
                
        # e.control is the ft.Container that was clicked.
        e.control.bgcolor = "#383838"
        
        chat_display.controls.clear()
        
        conv_id = e.control.data
        current_conversation_id = conv_id

        # --- 2. Dynamic Context Syncing ---
        # CORRECTLY get the conversation title from the Text widget's value.
        title = e.control.content.value
        
        detected_context = "EPB"
        for context_name in genai_service.context_files.keys():
            if f"[{context_name}]" in title:
                detected_context = context_name
                break
        
        context_dropdown.value = detected_context
        genai_service.set_system_prompt(detected_context)
        refresh_context_status_ui()

        # --- 3. Load and Display Messages ---
        messages = db_service.get_messages(conv_id)
        for msg in messages:
            is_user = msg["role"] == "user"
            
            if is_user:
                # Create the standard display row for user messages.
                message_view = ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Text("You", weight=ft.FontWeight.BOLD, color="#81d4fa"),
                            alignment=ft.Alignment.TOP_LEFT,
                            width=80
                        ),
                        ft.Markdown(
                            msg["content"],
                            selectable=True,
                            expand=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
                        )
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            else:
                # Use our helper function for bot messages.
                message_view = create_bot_response_view(page, msg["content"])

            chat_display.controls.append(message_view)
            
        page.update()
    
    async def on_keyboard(e: ft.KeyboardEvent):
        """Handle Ctrl+Enter to send messages."""
        if e.ctrl and e.key == "Enter":
            await send_message_click(None)

    async def delete_chat_click(e, conv_id):
        nonlocal current_conversation_id
        # 1. Delete from DB
        db_service.delete_conversation(conv_id)
        
        # 2. If we just deleted the active chat, reset the view
        if current_conversation_id == conv_id:
            await START_new_chat(None)
            
        # 3. Refresh the sidebar list
        await load_history_list()
        page.update()

    # Assign event handlers to the controls
    send_button.on_click = send_message_click
    input_field.on_submit = send_message_click
    page.on_keyboard_event = on_keyboard
    login_password_field.on_submit = login
    reg_password_field.on_submit = register
    
    # --------------------------------------------------------------------------
    # 5. UI Layout and Final Assembly
    # --------------------------------------------------------------------------

    # 1. Define the Login View Layout
    login_view = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=25,
        visible=True,
        # The main layout for the login screen is a Column that will hold
        # the Login fields, a Divider, and then the Registration fields.
        controls=[
            # --- Login Section ---
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=15,
                controls=[
                    ft.Text("Login", size=24, weight=ft.FontWeight.BOLD),
                    login_username_field,
                    login_password_field,
                    ft.FilledButton("Login", on_click=login, width=300, height=40)
                ],
            ),
            ft.Divider(height=20, thickness=1),

            # --- Registration Section ---
            ft.Column(
                spacing=15,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Register", size=24, weight=ft.FontWeight.BOLD),
                    reg_username_field,
                    reg_password_field,
                    ft.FilledButton("Register", on_click=register, width=300, height=40)
                ],
            ),
        ]
    )

    # 2. Define the Chat View Layout
    chat_view = ft.Row(
        visible=False,
        expand=True,
        controls=[
            ft.Container(
                width=300,
                padding=ft.Padding(0, 0, 10, 0),
                content=ft.Column(controls=[
                    history_list,
                    new_chat_button,
                ]),
            ),
            ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    ft.Container(
                        content=chat_display,
                        expand=True,
                        border=ft.Border.all(1, "#424242"),
                        border_radius=8,
                        padding=10,
                        bgcolor="#2d2d2d",
                    ),
                    ft.Container(
                        padding=ft.Padding(10, 0, 0, 0),
                        border=ft.Border.all(1, "#424242"),
                        border_radius=8,
                        bgcolor="#2d2d2d",
                        content=ft.Column(
                            spacing=4,
                            tight=True,
                            controls=[
                                ft.Row(
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        input_field,
                                        context_dropdown,
                                        settings_button,
                                        send_button,
                                    ],
                                ),
                                context_status_text,
                            ],
                        ),
                    ),
                ],
            ),
        ]
    )

    # 3. Drawer Logic
    async def open_drawer(e):
        page.end_drawer = my_fine_tune_drawer
        await page.show_end_drawer()
        page.update()

    settings_button.on_click = open_drawer

    # 4. Assembly - Use ONLY ONE page.add()
    # This prevents the overlapping/double-text issue.
    main_layout = ft.Column(
        [login_view, chat_view],
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    refresh_context_status_ui()
    page.add(main_layout)
    page.update()

# --- Application Entry Point ---
if __name__ == "__main__":
    ft.run(main)
