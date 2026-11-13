import requests
import time

BASE_URL = "http://127.0.0.1:8000/agent"


def send_message(message: str, conversation_id: int | None = None):
    payload = {
        "message": message,
        "conversation_id": conversation_id,
    }

    response = requests.post(BASE_URL, json=payload, timeout=60)
    response.raise_for_status()

    data = response.json()
    return data["response"], data["conversation_id"]


def main():
    conversation_id = None

    # Store a fact in the first message
    answer, conversation_id = send_message(
        "Kom ihåg detta: mitt hemliga kodord är BLÅBÄR."
    )

    print(f"Conversation ID: {conversation_id}")
    print(f"Agent: {answer}\n")

    # Push the first message outside the context window
    for i in range(12):
        answer, conversation_id = send_message(
            f"Detta är testmeddelande nummer {i + 1}. Svara endast OK.",
            conversation_id,
        )

        print(f"Message {i + 1}: {answer}")
        time.sleep(0.5)

    # Ask about the original fact
    answer, conversation_id = send_message(
        "Vad var mitt hemliga kodord?",
        conversation_id,
    )

    print("\n--- RESULTAT ---")
    print(f"Agentens svar: {answer}")

    if "BLÅBÄR" in answer.upper():
        print(
            "⚠️ Agenten svarade rätt trots att informationen borde vara utanför kontexten."
        )
    else:
        print("✅ Agenten kunde inte återge kodordet.")


if __name__ == "__main__":
    main()
