from src.distance import calculate_similarity, find_matching_philosophies

def test_similarity():
    # Test case: Identical scores (7 dimensions)
    scores1 = [5, 5, 5, 5, 5, 5, 5]
    scores2 = [5, 5, 5, 5, 5, 5, 5]
    dist = calculate_similarity(scores1, scores2)
    assert dist == 0.0, f"Expected 0.0, got {dist}"
    print("Test 1 passed: Identical scores (7-axis)")

    # Test case: Max distance (7 dimensions, 0-10 scale)
    scores3 = [10, 10, 10, 10, 10, 10, 10]
    scores4 = [0, 0, 0, 0, 0, 0, 0]
    dist = calculate_similarity(scores3, scores4)
    # sqrt(7 * 100) = sqrt(700) ≈ 26.46
    expected_max = 26.46
    assert abs(dist - expected_max) < 0.1, f"Expected ~{expected_max}, got {dist}"
    print(f"Test 2 passed: Max distance ({dist:.2f})")

def test_matching():
    # Test if we get results from CSV (7-axis)
    # 실존주의 점수: [10, 5, 1, 4, 6, 2, 2]
    user_scores = [10, 5, 1, 4, 6, 2, 2]
    results = find_matching_philosophies(user_scores)
    assert len(results) > 0, "Should return matching results"
    assert results[0]['philosophy'] == "실존주의", f"Expected 실존주의, got {results[0]['philosophy']}"
    print(f"Test 3 passed: Matching works (Top: {results[0]['philosophy']})")
    
    # Test 스토아 matching
    stoic_scores = [8, 9, 5, 6, 5, 4, 7]
    results_stoic = find_matching_philosophies(stoic_scores)
    assert results_stoic[0]['philosophy'] == "스토아", f"Expected 스토아, got {results_stoic[0]['philosophy']}"
    print(f"Test 4 passed: Stoic matching (Top: {results_stoic[0]['philosophy']})")

def test_csv_structure():
    """CSV 구조 검증"""
    from src.distance import load_philosophy_data
    data = load_philosophy_data()
    
    assert len(data) == 12, f"Expected 12 philosophies, got {len(data)}"
    print(f"Test 5 passed: 12 philosophies loaded")
    
    # 7축 점수 확인
    for item in data:
        assert len(item['scores']) == 7, f"Expected 7 scores for {item['philosophy']}, got {len(item['scores'])}"
    print("Test 6 passed: All philosophies have 7 scores")
    
    # 키워드 컬럼 확인
    assert 'core_keywords' in data[0], "Missing core_keywords column"
    print("Test 7 passed: Keyword columns exist")

if __name__ == "__main__":
    test_similarity()
    test_matching()
    test_csv_structure()
    print("\n✅ All tests passed!")
