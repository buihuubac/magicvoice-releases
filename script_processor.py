"""
script_processor.py — Tiền xử lý script trước khi TTS đọc
Nguyên tắc: Câu ngắn · Có nhịp · Có chỗ ngắt · Giống cách nói chuyện
"""
import re

# Từ nối → điểm ngắt tự nhiên
CLAUSE_BREAKS = [
    # Liên từ đối lập → ngắt mạnh
    r'\b(but|however|yet|although|though|even though|whereas|while)\b',
    # Liên từ nhân quả → ngắt vừa
    r'\b(because|since|so|therefore|thus|hence|as a result)\b',
    # Liên từ thời gian → ngắt nhẹ
    r'\b(when|while|as|after|before|until|once|whenever)\b',
    # Mệnh đề quan hệ → ngắt nhẹ
    r'\b(which|who|whose|whom|where)\b',
    # Liên từ bổ sung → ngắt nhẹ
    r'\b(and|plus|also|moreover|furthermore|in addition)\b',
]

def split_at_clause(sentence: str, max_words: int = 12) -> list[str]:
    """Tách câu dài tại điểm ngắt tự nhiên."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]

    # Tìm điểm ngắt gần giữa câu nhất
    mid = len(words) // 2
    best_split = None
    best_dist = float('inf')

    for i, word in enumerate(words[2:], start=2):
        clean = word.lower().strip('.,;:!?')
        is_break = any(re.match(p, clean) for p in CLAUSE_BREAKS)
        if is_break:
            dist = abs(i - mid)
            if dist < best_dist:
                best_dist = dist
                best_split = i

    if best_split:
        left  = " ".join(words[:best_split])
        right = " ".join(words[best_split:])
        return split_at_clause(left, max_words) + split_at_clause(right, max_words)
    else:
        # Không tìm thấy điểm ngắt → cắt ở dấu phẩy hoặc giữa câu
        for i in range(mid-2, mid+3):
            if 0 < i < len(words) and words[i].endswith(','):
                left  = " ".join(words[:i+1])
                right = " ".join(words[i+1:])
                return [left, right]
        # Cắt ở giữa cứng
        return [" ".join(words[:mid]), " ".join(words[mid:])]


def add_rhythm_pauses(segments: list[str]) -> list[tuple[str, float]]:
    """
    Thêm pause phù hợp dựa trên nội dung và dấu câu.
    Returns: [(text, pause_seconds), ...]
    """
    result = []
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue

        last = seg.rstrip()[-1:] if seg else ''

        # Xác định pause dựa trên dấu câu cuối
        if last in '.!?':
            pause = 0.65   # Kết thúc câu → nghỉ dài
        elif last == ',':
            pause = 0.28   # Dấu phẩy → nghỉ ngắn
        elif last == ';':
            pause = 0.45   # Dấu chấm phẩy → nghỉ vừa
        elif last == ':':
            pause = 0.35   # Dấu hai chấm → ngắt vừa
        else:
            # Không có dấu (đoạn tách từ liên từ) → nghỉ nhẹ
            pause = 0.38

        # Sau câu hỏi / cảm thán → kéo dài thêm chút
        if last in '?!':
            pause += 0.15

        # Đoạn cuối → không cần pause
        if i == len(segments) - 1:
            pause = 0.0

        result.append((seg, pause))
    return result


def optimize_for_tts(txt: str, max_words_per_segment: int = 11) -> list[tuple[str, float]]:
    """
    Tối ưu toàn bộ text cho TTS.
    1. Tách đoạn văn
    2. Tách câu
    3. Tách mệnh đề dài
    4. Thêm pause tự nhiên

    Returns: [(segment_text, pause_seconds), ...]
    """
    # Bước 1: Tách đoạn văn
    paragraphs = [p.strip() for p in txt.splitlines() if p.strip()]

    all_segments = []

    for pi, para in enumerate(paragraphs):
        # Bước 2: Tách câu
        sentences = re.split(r'(?<=[.!?])\s+', para)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Bước 3: Tách mệnh đề nếu câu quá dài
            clauses = split_at_clause(sentence, max_words=max_words_per_segment)
            all_segments.extend(clauses)

        # Sau đoạn văn → pause dài hơn (trừ đoạn cuối)
        if pi < len(paragraphs) - 1 and all_segments:
            # Tăng pause của segment cuối đoạn văn
            last_seg, last_pause = all_segments[-1]
            all_segments[-1] = (last_seg, max(last_pause, 0.9))

    # Bước 4: Thêm pause tự nhiên
    result = add_rhythm_pauses(all_segments)
    return result


def preview_script(txt: str) -> str:
    """Tạo preview script đã tối ưu để user xem trước."""
    segments = optimize_for_tts(txt)
    lines = []
    for seg, pause in segments:
        pause_mark = ""
        if pause >= 0.6:
            pause_mark = " ‖"      # Nghỉ dài
        elif pause >= 0.35:
            pause_mark = " |"      # Nghỉ vừa
        elif pause >= 0.2:
            pause_mark = " ·"      # Nghỉ ngắn
        lines.append(f"{seg}{pause_mark}")
    return "\n".join(lines)


# Test
if __name__ == "__main__":
    test = """She said it the way people say things when they've decided the person in front of them doesn't warrant the courtesy of a lowered voice. The old man's hands went still on the counter. The coins stopped moving. And Keanu Reeves, standing three feet behind him in line with a bottle of water and a granola bar, heard every word."""

    print("=== ORIGINAL ===")
    print(test)
    print("\n=== OPTIMIZED PREVIEW ===")
    print(preview_script(test))
    print("\n=== SEGMENTS WITH PAUSES ===")
    for seg, pause in optimize_for_tts(test):
        print(f"[{pause:.2f}s] {seg}")
