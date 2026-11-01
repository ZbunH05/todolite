"""Thầy tử vi: luận giải qua API kiểu OpenAI (mặc định DeepSeek), chưa có key thì luận mẫu ngay tại máy.

Thư viện mạng chỉ được nạp trong stream_answer, nên mở trang Tử vi không làm nặng giao diện.
"""
import json

from . import lunar
from .schedule import WEEKDAY_LONG

TIMEOUT = 40
TEMPERATURE = 0.8
MAX_TOKENS = 800
HISTORY_LIMIT = 6  # số tin nhắn trước đó gửi kèm để AI nhớ mạch trò chuyện
SUGGESTIONS = ("Lá số tử vi nói gì về đường tình duyên của tôi?", "Công việc hiện tại của tôi có phù hợp hay không?",
               "Tình hình tài chính của tôi trong tương lai như thế nào?", "Hôm nay tôi nên ưu tiên điều gì để mọi việc thuận hơn?")
SYSTEM_PROMPT = ("Bạn là thầy tử vi người Việt, nói chuyện ấm áp, gần gũi và thực tế. Hãy trả lời bằng tiếng Việt, dựa trên "
                 "dữ kiện lịch được cung cấp, không tự đổi ngày hay can chi. Chia câu trả lời thành ba phần với tiêu đề Markdown: "
                 "## Tổng quan, ## Điểm sáng, ## Lời nhắc. Mỗi phần tối đa ba câu. Đây là nội dung tham khảo để chiêm "
                 "nghiệm: không khẳng định chắc chắn về tương lai, không đưa lời khuyên y tế, pháp lý hay đầu tư cụ thể.")
TOPICS = ((("tình", "yêu", "duyên", "hôn nhân", "vợ", "chồng"),
           "Chuyện tình cảm hôm nay cần sự chân thành: nói rõ điều mình mong muốn và lắng nghe trước khi kết luận."),
          (("công việc", "sự nghiệp", "nghề", "học", "thi"),
           "Công việc và học tập tiến triển khi bạn tập trung vào một mục tiêu rõ ràng, làm xong việc quan trọng nhất trước."),
          (("tài chính", "tiền", "thu nhập", "lương", "đầu tư"),
           "Về tiền bạc, hãy giữ kỷ luật chi tiêu và cân nhắc kỹ các khoản lớn, đừng quyết định theo cảm xúc."))
GENERAL_TOPIC = "Hôm nay hợp với việc sắp xếp lại ưu tiên và làm trọn từng việc nhỏ, đừng ôm đồm cùng lúc."
GOOD_DAY = "Ngày {spirit} là ngày hoàng đạo, thuận cho việc khởi đầu và gặp gỡ."
BAD_DAY = "Ngày {spirit} là ngày hắc đạo, nên ưu tiên việc quen tay và chuẩn bị kỹ, để dành chuyện lớn cho ngày khác."
OFFLINE_NOTE = "Đây là bản luận mẫu tạo ngay trên máy từ dữ kiện lịch, chưa dùng AI. Thêm API key trong Cài đặt để hỏi chi tiết hơn."


def _hours(day):
    return ", ".join(hour.name for hour in lunar.good_hours(day))


def day_facts(day):
    """Dữ kiện lịch của ngày xem, mỗi dòng một nhãn."""
    converted = lunar.solar_to_lunar(day)
    spirit, good = lunar.day_spirit(day)
    return [f"Dương lịch: {WEEKDAY_LONG[day.weekday()]}, {day:%d/%m/%Y}", f"Âm lịch: {lunar.lunar_text(converted)}",
            f"Năm âm lịch: {lunar.year_can_chi(converted.year)}", f"Can chi ngày: {lunar.day_can_chi(day)}",
            f"Can chi tháng: {lunar.month_can_chi(converted.month, converted.year)}", f"Giờ mở đầu: {lunar.first_hour_can_chi(day)}",
            f"Trực ngày: {spirit}, {'hoàng đạo' if good else 'hắc đạo'}", f"Giờ hoàng đạo: {_hours(day)}"]


def birth_lunar(birth):
    """Ngày âm của ngày sinh kèm can chi. Năm tính theo âm lịch: người sinh trước Tết thuộc năm cũ."""
    converted = lunar.solar_to_lunar(birth)
    return f"{lunar.lunar_text(converted)} năm {lunar.year_can_chi(converted.year)}, tuổi {lunar.year_zodiac(converted.year)}"


def birth_text(birth):
    return f"{birth:%d/%m/%Y}, tức {birth_lunar(birth)}"


def build_messages(question, day, birth=None, history=()):
    lines = day_facts(day)
    if birth:
        lines.append(f"Ngày sinh: {birth_text(birth)}")
    lines.append(f"Câu hỏi người dùng: {question}")
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history[-HISTORY_LIMIT:], {"role": "user", "content": "\n".join(lines)}]


def offline_answer(question, day, birth=None):
    """Luận mẫu khi chưa có API key, không gửi gì ra ngoài."""
    text = question.lower()
    topic = next((sentence for words, sentence in TOPICS if any(word in text for word in words)), GENERAL_TOPIC)
    converted = lunar.solar_to_lunar(day)
    spirit, good = lunar.day_spirit(day)
    context = [f"{day:%d/%m/%Y}, tức {lunar.lunar_text(converted)} năm {lunar.year_can_chi(converted.year)}.",
               f"Ngày {lunar.day_can_chi(day)}, tháng {lunar.month_can_chi(converted.month, converted.year)}, giờ tốt: {_hours(day)}."]
    if birth:
        context.append(f"Người sinh ngày {birth_text(birth)}.")
    reminder = (GOOD_DAY if good else BAD_DAY).format(spirit=spirit)
    return f"## Tổng quan\n{topic}\n\n## Bối cảnh ngày xem\n{' '.join(context)}\n\n## Lời nhắc\n{reminder}\n\n{OFFLINE_NOTE}"


def answer_runs(text):
    """Tách Markdown thành các đoạn (chữ, kiểu) để hiển thị, kiểu là 'heading', 'bold' hoặc None.

    Câu trả lời về từng mảnh nên dấu ** có thể chưa khép: đoạn dở dang vẫn được coi là đậm.
    """
    runs = []
    for line in text.strip().replace("\n\n#", "\n#").split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            runs.append((stripped.lstrip("#").replace("**", "").strip() + "\n", "heading"))
            continue
        if stripped[:2] in ("- ", "* "):
            line = "• " + stripped[2:]
        for index, part in enumerate(line.split("**")):
            if part:
                runs.append((part, "bold" if index % 2 else None))
        runs.append(("\n", None))
    return runs


def _piece(line):
    """Chữ trong một dòng SSE 'data: {...}'. Dòng khác và phần suy nghĩ của mô hình thì bỏ qua."""
    if not line.startswith(b"data:"):
        return None
    choices = json.loads(line[5:]).get("choices") or [{}]
    return (choices[0].get("delta") or {}).get("content")


def _problem(error, read_json):
    """Lời giải thích dễ hiểu cho một phản hồi lỗi."""
    code = error.code
    with error:
        detail = read_json(error.read()).get("error")
    if code in (401, 403):
        return "API key không đúng hoặc đã hết hạn"
    if code == 402:
        return "Tài khoản AI đã hết số dư"
    if code == 404:
        return "API URL hoặc tên model không đúng"
    if code == 429:
        return "Máy chủ AI đang giới hạn lượt gọi. Vui lòng thử lại sau"
    if code >= 500:
        return "Máy chủ AI đang gặp sự cố. Vui lòng thử lại sau"
    return (detail.get("message") if isinstance(detail, dict) else None) or f"Máy chủ AI báo lỗi {code}"


def request_body(url, model, messages):
    body = {"model": model, "messages": messages, "stream": True, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS}
    if "deepseek.com" in url:
        body["thinking"] = {"type": "disabled"}  # DeepSeek bật mặc định: trả lời chậm, tốn max_tokens, bỏ qua temperature
    return body


def stream_answer(url, key, model, messages):
    """Sinh từng mảnh chữ của câu trả lời. Mọi lỗi được báo bằng ApiError với lời giải thích dễ hiểu."""
    import urllib.error
    import urllib.request

    from .web import NETWORK_ERRORS, ApiError, check_api_url, read_json

    request = urllib.request.Request(check_api_url(url), data=json.dumps(request_body(url, model, messages)).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    received = False
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            for raw in response:
                line = raw.strip()
                if line == b"data: [DONE]":
                    break
                piece = _piece(line)
                if piece:
                    received = True
                    yield piece
    except urllib.error.HTTPError as error:
        raise ApiError(_problem(error, read_json), permanent=True) from None
    except NETWORK_ERRORS as error:
        slow = isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)
        raise ApiError("Máy chủ AI phản hồi quá chậm. Vui lòng thử lại." if slow
                       else "Không kết nối được tới máy chủ AI lúc này.") from None
    if not received:
        raise ApiError("Máy chủ AI chưa trả về nội dung hợp lệ.")
