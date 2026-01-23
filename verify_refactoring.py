from src.distance import calculate_similarity, find_matching_philosophies

def test_similarity():
    # Test case: Identical scores
    scores1 = [0.5, 0.5, 0.5, 0.5]
    scores2 = [0.5, 0.5, 0.5, 0.5]
    dist = calculate_similarity(scores1, scores2)
    assert dist == 0.0, f"Expected 0.0, got {dist}"
    print("Test 1 passed: Identical scores")

    # Test case: Max distance
    scores3 = [1.0, 1.0, 1.0, 1.0]
    scores4 = [0.0, 0.0, 0.0, 0.0]
    dist = calculate_similarity(scores3, scores4)
    assert dist == 2.0, f"Expected 2.0, got {dist}"
    print("Test 2 passed: Max distance")

def test_matching():
    # Test if we get results from CSV
    user_scores = [0.9, 0.4, 0.9, 0.7] # Existentialism-like
    results = find_matching_philosophies(user_scores)
    assert len(results) > 0, "Should return matching results"
    assert results[0]['philosophy'] == "실존주의", f"Expected 실존주의, got {results[0]['philosophy']}"
    print(f"Test 3 passed: Matching works (Top: {results[0]['philosophy']})")

if __name__ == "__main__":
    test_similarity()
    test_matching()
    print("All tests passed!")
