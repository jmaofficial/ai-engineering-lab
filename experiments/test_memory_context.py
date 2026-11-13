from app.api.dependencies import get_agent_service


def main():
    # Create agent with existing dependencies
    dependency = get_agent_service()
    agent = next(dependency)

    try:
        # Create a conversation with an important fact
        response, conversation_id = agent.run(message="Mitt hemliga kodord är BLÅBÄR.")

        print(f"Conversation ID: {conversation_id}")

        # Push the fact outside the sliding window
        for i in range(12):
            agent.run(
                message=f"Testmeddelande {i + 1}. Svara endast OK.",
                conversation_id=conversation_id,
            )

        question = "Vad var mitt hemliga kodord?"

        # Test A: Without memory
        response_a, _ = agent.run(
            message=question,
            conversation_id=conversation_id,
        )

        print("\n--- TEST A: SLIDING WINDOW ---")
        print(response_a)

        # Test B: With memory
        response_b, _ = agent.run(
            message=question,
            conversation_id=conversation_id,
            memories=["User's secret codeword is BLÅBÄR."],
        )

        print("\n--- TEST B: MEMORY-AUGMENTED ---")
        print(response_b)

        print("\n--- RESULTS ---")
        print("Without memory:", "BLÅBÄR" in response_a.upper())
        print("With memory:", "BLÅBÄR" in response_b.upper())

    finally:
        dependency.close()


if __name__ == "__main__":
    main()
