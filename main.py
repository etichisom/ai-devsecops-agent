import anthropic
from rich.console import Console
from rich.status import Status
from ai_agent import AIAgent

api_key = ''
client = anthropic.Anthropic(api_key=api_key)



console = Console()
ai_agent = AIAgent(api_key=api_key)
print("AI Code Assistant")
print("================")
print("A conversational AI agent that can read, list, and edit files.")
print("Type 'exit' or 'quit' to end the conversation.")
print()

while True:
    try:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit']:
            print("Goodbye!!!!!!!!")
            break
        if not  user_input:
            continue
        console.print("\n[bold cyan]Assistant:[/bold cyan] ", end="")

        with console.status(
                "[bold cyan]Thinking...[/bold cyan]",
                spinner="dots",
        ):
            response = ai_agent.chat(user_input)
        console.print(response)
        print()

    except Exception as e:
            print("Goodbye!!!!!!!!")
            break
