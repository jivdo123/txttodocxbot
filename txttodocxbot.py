import os
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from docx import Document

# --- Paste your bot token here ---
TELEGRAM_BOT_TOKEN = '8112681572:AAHXFkLmUkwsRxcpx8GN0FCvd8gsnxFOk3I'

# --- Configuration ---
# Sets the maximum number of questions per DOCX file.
QUESTIONS_PER_FILE = 30

# This function remains from your original code to parse a text block.
def parse_text_question(block: str):
    """
    Parses a single block of text based on a fixed line structure.
    """
    block = block.strip()
    if not block:
        return None

    lines = [line.strip() for line in block.split('\n') if line.strip()]

    if len(lines) < 5:
        raise ValueError("The question block is incomplete. It must have a question and at least four options.")

    correct_option_match = re.search(r'Correct Option:\s*(\S+)', block, re.IGNORECASE)
    if not correct_option_match:
        raise ValueError("The 'Correct Option: [id]' line is missing.")
    correct_option_id = correct_option_match.group(1).lower()

    question_text = re.sub(r'^(?:\d+\.|Q\.)\s*', '', lines[0])

    parsed_options = []
    option_ids = ['a', 'b', 'c', 'd']
    for i in range(4):
        option_line = lines[i + 1]
        option_text = re.sub(r'^[a-zA-Z\d]+[\.\)]\s*', '', option_line)
        parsed_options.append({'id': option_ids[i], 'text': option_text})
    
    explanation_text = ""
    if len(lines) > 5:
        explanation_lines = []
        for line in lines[5:]:
            if 'Correct Option:' not in line:
                explanation_lines.append(line)
        explanation_text = "\n".join(explanation_lines).strip()

    return {
        'question_text': question_text,
        'options': parsed_options,
        'correct_option_id': correct_option_id,
        'explanation_text': explanation_text
    }

# This function to create the DOCX is unchanged and works perfectly.
def create_docx(questions_data, file_path):
    """
    Generates a .docx file with a separate, fixed-structure table for each question.
    """
    doc = Document()
    
    for q_data in questions_data:
        table = doc.add_table(rows=0, cols=3)
        table.style = 'Table Grid'
        
        # --- 1. Question Row ---
        row_cells = table.add_row().cells
        row_cells[0].text = 'Question'
        row_cells[1].merge(row_cells[2]).text = q_data['question_text']

        # --- 2. Type Row ---
        row_cells = table.add_row().cells
        row_cells[0].text = 'Type'
        row_cells[1].merge(row_cells[2]).text = 'multiple_choice'

        # --- 3. Option Rows ---
        correct_id = q_data.get('correct_option_id')
        correct_index = q_data.get('correct_option_index')

        for i, option in enumerate(q_data['options']):
            row_cells = table.add_row().cells
            row_cells[0].text = 'Option'
            row_cells[1].text = option['text']
            
            is_correct = False
            if correct_id is not None:
                if option.get('id', '').lower() == correct_id.lower():
                    is_correct = True
            elif correct_index is not None:
                if i == correct_index:
                    is_correct = True
            
            row_cells[2].text = 'correct' if is_correct else 'incorrect'

        # --- 4. Solution Row ---
        row_cells = table.add_row().cells
        row_cells[0].text = 'Solution'
        row_cells[1].merge(row_cells[2]).text = q_data['explanation_text']

        # --- 5. Marks Row ---
        row_cells = table.add_row().cells
        row_cells[0].text = 'Marks'
        row_cells[1].text = '4'
        row_cells[2].text = '1'

        doc.add_paragraph('')
        
    doc.save(file_path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    await update.message.reply_text(
        "Hello! \U0001F44B\n"
        "Please send me a .txt file with your questions, or forward a Telegram Quiz.\n\n"
        "I will convert them into a structured .docx file for you. "
        f"If the file has more than {QUESTIONS_PER_FILE} questions, I'll create multiple documents."
    )

# --- NEW: HANDLER FOR .TXT FILE UPLOADS ---
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles .txt file uploads, parses questions, and creates batched .docx files."""
    chat_id = update.message.chat_id
    doc = update.message.document

    # 1. Download the file from Telegram
    await update.message.reply_text(f"Processing your file: {doc.file_name} ... \u23F3")
    temp_txt_path = f'input_{chat_id}.txt'
    file = await doc.get_file()
    await file.download_to_drive(temp_txt_path)

    # 2. Read and parse the entire file content
    try:
        with open(temp_txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        await update.message.reply_text(f"\U0001F198 Error reading file: {e}")
        os.remove(temp_txt_path)
        return
        
    question_blocks = re.split(r'\n\s*\n', content.strip())
    valid_questions = []
    failed_blocks = []

    for i, block in enumerate(question_blocks):
        if not block.strip(): continue
        try:
            parsed_q = parse_text_question(block)
            if parsed_q:
                valid_questions.append(parsed_q)
        except ValueError as e:
            failed_blocks.append(f"\U0001F198 ERROR IN QUESTION #{i+1}\nReason: {e}")

    # 3. Report any parsing errors
    if failed_blocks:
        error_summary = "\n\n".join(failed_blocks)
        await update.message.reply_text(f"Found some issues in your file:\n\n{error_summary}")

    # 4. Process valid questions and create batched DOCX files
    if valid_questions:
        total_q = len(valid_questions)
        num_files = (total_q + QUESTIONS_PER_FILE - 1) // QUESTIONS_PER_FILE
        
        await update.message.reply_text(
            f"\u2705 Successfully parsed {total_q} question(s). "
            f"Generating {num_files} DOCX file(s) for you now..."
        )
        
        # Split valid_questions into chunks of 30
        for i in range(0, total_q, QUESTIONS_PER_FILE):
            chunk = valid_questions[i:i + QUESTIONS_PER_FILE]
            part_num = (i // QUESTIONS_PER_FILE) + 1
            
            output_doc_path = f'questions_{chat_id}_part_{part_num}.docx'
            create_docx(chunk, output_doc_path)
            
            await update.message.reply_document(document=open(output_doc_path, 'rb'))
            os.remove(output_doc_path) # Clean up the generated docx file
            
    elif not failed_blocks:
        await update.message.reply_text("\u274C No valid questions found in the file.")
        
    # 5. Clean up the original downloaded txt file
    os.remove(temp_txt_path)


# The handler for quizzes remains unchanged.
async def handle_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles native Telegram quizzes."""
    chat_id = update.message.chat_id
    poll = update.message.poll
    
    if poll.type != 'quiz':
        await update.message.reply_text("This looks like a regular poll, not a quiz. I can only process quizzes.")
        return

    await update.message.reply_text("Processing quiz... \u23F3")

    quiz_data = {
        'question_text': poll.question,
        'options': [{'text': opt.text} for opt in poll.options],
        'correct_option_index': poll.correct_option_id,
        'explanation_text': poll.explanation or ""
    }

    file_path = f'quiz_{chat_id}.docx'
    create_docx([quiz_data], file_path)
    
    await update.message.reply_text(f"\u2705 Successfully processed the quiz.")
    await update.message.reply_document(document=open(file_path, 'rb'))
    os.remove(file_path)


def main():
    """Starts the bot and adds all handlers."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    
    # --- MODIFIED: This handler now specifically listens for .txt documents ---
    application.add_handler(MessageHandler(filters.Document.TXT, handle_document))
    
    # Handler for quizzes remains the same
    application.add_handler(MessageHandler(filters.POLL, handle_quiz))
    
    # Optional: Add a message for plain text to guide users
    async def guide_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Please send your questions as a .txt file. I no longer process plain text messages.")
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, guide_user))
    
    print("Bot started... (Press Ctrl+C to stop)")
    application.run_polling()

if __name__ == '__main__':
    main()
