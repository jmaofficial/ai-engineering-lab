import requests

BASE_URL = "http://127.0.0.1:8000/agent"


def send_message(message, conversation_id=None):
    response = requests.post(
        BASE_URL,
        json={
            "message": message,
            "conversation_id": conversation_id,
        },
        timeout=120,
    )

    if not response.ok:
        print(f"HTTP STATUS: {response.status_code}")
        print(f"ERROR RESPONSE: {response.text}")

    response.raise_for_status()
    return response.json()


def main():
    conversation_id = None

    for i in range(10):
        message = (
            "Jag bygger mitt AI-projekt i Python och använder PostgreSQL."
            if i == 0
            else f"Testmeddelande {i}. Svara endast OK."
        )

        result = send_message(message, conversation_id)
        conversation_id = result["conversation_id"]

        print(f"Message {i + 1}/10 sent")

    print(f"\nConversation ID: {conversation_id}")
    print("Check the memories table in PostgreSQL!")


if __name__ == "__main__":
    main()
