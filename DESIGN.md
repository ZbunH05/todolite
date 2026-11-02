# Thiết kế TodoLite

Giao diện được duyệt lại theo phương pháp của [Impeccable](https://github.com/pbakaus/impeccable). App là công cụ làm việc hằng ngày, nên người dùng phải biết mọi thứ nằm ở đâu trước khi để ý tới phong cách. Phong cách chỉ góp bốn thứ: màu, chữ, mật độ và một dấu ấn riêng. Điều hướng và điều khiển giữ đúng thói quen của app Windows.

Bộ quét tự động của Impeccable chỉ đọc giao diện web, nên với app Tk việc kiểm tra dựa trên ảnh chụp thật, kịch bản bấm thật và phép đo tương phản. Xem `theme.py` để biết giá trị màu.

## Dấu ấn riêng

- **Khung xanh đen:** thanh bên và thanh tiêu đề dùng chung một màu `RAIL`, giữ nguyên ở cả hai theme. Đổi theme chỉ đổi phần bên trong.
- **Dải 12 giờ:** ngày chia theo 12 giờ âm lịch. Ô xanh là giờ hoàng đạo, thanh dưới là khối giờ, hình thoi là hạn trong ngày, vạch đỏ là bây giờ. Dải này nối to-do với lịch vạn niên, điều mà app to-do thường không có.
- **Tờ lịch:** chi tiết ngày đọc như tờ lịch treo tường, số ngày thật lớn, ngày âm đối diện.

## Màu

Mỗi màu có một vai trò, không dùng để trang trí.

| Vai trò | Token | Dùng cho |
|---|---|---|
| Khung | `RAIL`, `RAIL_HOVER`, `RAIL_TEXT`, `RAIL_MUTED` | Thanh bên, thanh tiêu đề |
| Nền | `BG`, `CARD`, `FIELD`, `SUNKEN` | Nền trang, thẻ, ô nhập, ô ngoài tháng |
| Chữ | `TEXT`, `MUTED` | Nội dung và phần phụ |
| Hành động | `FILL`, `FILL_HOVER`, `ACCENT`, `ACCENT_SOFT` | Nút chính, đang chọn, đang chạy |
| Tốt | `GREEN`, `GREEN_SOFT`, `GREEN_SOFT_HOVER`, `GREEN_EDGE` | Nên làm, giờ hoàng đạo, ngày tốt, đã xong, giờ nghỉ Pomodoro |
| Xấu | `RED`, `RED_SOFT`, `RED_SOFT_HOVER`, `RED_EDGE` | Kiêng kỵ, ngày xấu, quá hạn |
| Lưu ý | `AMBER`, `AMBER_SOFT` | Ngày trung bình, hạn sắp tới, ngày lễ |

Mọi cặp chữ và nền đạt tối thiểu 4,5:1 ở cả hai theme. Không truyền đạt ý nghĩa chỉ bằng màu: ngày xấu là tam giác, ngày tốt là chấm tròn, ô nên và kiêng có tiêu đề chữ.

## Chữ

Một họ chữ Be Vietnam Pro, đi kèm app trong `assets/fonts` theo giấy phép SIL OFL. Font được nạp riêng cho tiến trình, không cài vào Windows; thiếu file thì app lùi về Segoe UI Variable. Chỉ dùng hai độ đậm là Regular và SemiBold: hiển thị qua GDI, Medium gần đậm bằng SemiBold nên không tạo được bậc nào mới.

Cỡ chữ theo vai trò, không dùng số nào khác:

| Cỡ | Vai trò |
|---|---|
| 12 | Ghi chú, căn cứ của lời khuyên |
| 13 | Nội dung phụ, nút |
| 14 | Nội dung chính |
| 16 | Tiêu đề khối |
| 24 | Tiêu đề trang |
| 32 | Số liệu |
| 48 | Đồng hồ đếm ngược |
| 72 | Số ngày trên tờ lịch, đồng hồ Pomodoro |

Riêng ô lịch rất dày được dùng cỡ 11 cho ngày âm và giờ.

Dòng chữ cao khoảng 1,5 lần cỡ chữ, cao hơn Segoe: cỡ 14 là 22, cỡ 13 là 19, cỡ 12 là 18. Chiều cao và bề rộng viết tay phải tính theo đó.

Tuỳ chọn **Cỡ chữ** trong Cài đặt có ba mức Vừa, Lớn, Rất lớn, tức hệ số 1, 1,15 và 1,3. Hệ số nhân vào toàn bộ bố cục như phóng to, nên tỉ lệ giữ nguyên và cửa sổ tối thiểu lớn theo. Đổi mức có hiệu lực ngay, các trang đã dựng tự theo, không cần mở lại app.

## Bề mặt

Bo góc có ba mức, là token trong `theme.py`:

| Token | Bán kính | Dùng cho |
|---|---:|---|
| `RADIUS_CARD` | 12 | Thẻ, thẻ việc, thanh thông báo |
| `RADIUS_CONTROL` | 8 | Nút, ô nhập, ô lịch, khối màu trong thẻ, pill thanh bên |
| `RADIUS_CHIP` | 6 | Mục trên lịch, nhãn mức kỵ, ô đánh dấu |

Chip bật tắt là ngoại lệ có chủ đích: bo tròn hẳn hai đầu, để phân biệt với nút.

- **Thẻ việc:** mỗi việc là một thẻ riêng trên nền trang, cách nhau 6, không có thẻ lớn nào bọc ngoài. Viền 1 px như mọi thẻ khác, không có bóng. Rê chuột đổi sang `CARD_HOVER`, đang chọn là `ACCENT_SOFT` kèm viền `ACCENT` 1 px.
- **Thẻ việc theo trạng thái:** việc quá hạn có nền `RED_SOFT`, viền `RED_EDGE`, vòng tròn đỏ; việc đã xong có nền `GREEN_SOFT`, viền `GREEN_EDGE`, dấu tích và tên việc màu `GREEN`. Đang chọn vẫn thắng màu trạng thái. Màu không đứng một mình: việc quá hạn nằm trong nhóm Quá hạn và ghi `trễ 2 giờ`, việc đã xong có dấu tích, chữ gạch ngang và `Xong lúc`. Nền rê chuột của thẻ đỏ pha nhạt hơn để chữ đỏ cỡ 12 vẫn đạt 4,5:1 ở theme sáng.
- **Nhóm việc:** tiêu đề nhóm nói gì thì dòng việc không nói lại. Sắp tới chia theo từng ngày trong 14 ngày tới, xa hơn thì theo tháng. Dòng trong nhóm theo ngày chỉ ghi giờ, việc cả ngày không ghi gì; dòng trong nhóm theo tháng ghi ngày và giờ; riêng nhóm Quá hạn ghi đủ.
- **Thanh bên:** mục đang chọn là một pill `FILL`, rê chuột là pill `RAIL_HOVER`. Danh sách tag dài thì cuộn theo từng dòng nguyên, một vạch mảnh báo còn tag phía trên hoặc phía dưới.
- **Con trượt:** mảnh 3 px kiểu Windows 11, nằm trong rãnh riêng 12 px chứ không đè lên thẻ. Hiện khi cuộn hoặc khi con trỏ vào vùng cuộn, rê tới thì to ra 6 px, đứng yên 1 giây thì ẩn, nội dung vừa khung thì không có. Màu `MUTED` pha với nền, rê tới thì `MUTED` đặc.
- **Widget nhẹ:** chữ tĩnh dùng `widgets.Label` (một cửa sổ Tk), không dùng CTkLabel. Thứ lặp lại nhiều như chip và dải số liệu thì tự vẽ trên một Canvas, giữ đúng cỡ và vị trí chữ của widget CustomTkinter tương ứng. Widget CustomTkinter chỉ dùng cho nút, ô nhập và khung cần nền bo góc.
- **Canvas:** mọi hình bo góc vẽ bằng `shapes.rounded()`, truyền đúng màu ngay phía sau hình. Đa giác của Tk không khử răng cưa. Canvas không tự bo góc được, nên phải chừa 5 px khỏi mép thẻ, hoặc tự vẽ viền thẻ như lịch.

## Chuyển động

Chuyển động chỉ để báo trạng thái đổi, luôn nhanh, không nảy, không có màn chào khi mở app.

| Chuyển động | Thời gian | Đường cong |
|---|---:|---|
| Pill thanh bên trượt tới mục mới | 160 ms | chậm dần bậc ba |
| Nội dung mờ dần khi đổi trang, tab, chế độ lịch, mở đóng panel chi tiết, đổi theme, đổi cỡ chữ | 160 ms | chậm dần bậc ba |
| Một nấc con lăn | khoảng 170 ms | đuổi theo đích theo hàm mũ |
| Bàn di chuột | bám ngón tay, dừng sau nấc cuối khoảng 40 ms | làm mượt rất nhẹ |

- **Chuyển động có chủ đích duy nhất:** pill của mục đang chọn trượt sang mục mới trong lúc nội dung mờ dần. Mọi thứ khác đứng yên.
- **Chuyển cảnh:** ảnh chụp của vùng cũ phủ lên rồi mờ đi, trang mới đã nằm sẵn bên dưới, nên không bao giờ thấy trang vẽ dở. Trang dựng lần đầu chậm thì ảnh cũ đứng yên cho tới khi xong. Đổi việc trong panel đang mở chỉ làm mờ panel.
- **Cuộn:** mỗi nấc dời theo số dòng trong cài đặt chuột của Windows, 36 điểm ảnh một dòng ở cỡ chữ Vừa. Nấc dồn dập thì cộng dồn, tới hai đầu thì dừng đúng mép, không bật lại. Chỗ lật từng bước như tháng trong Vạn niên thì mỗi nấc con lăn lật một tháng, mỗi lần vuốt bàn di chuột cũng chỉ lật một tháng. Tag trên thanh bên cuộn theo dòng nguyên, mỗi nấc bằng số dòng của Windows.
- **Tôn trọng cài đặt của Windows:** tắt **Settings → Accessibility → Visual effects → Animation effects** thì cuộn nhảy thẳng tới đích, đổi trang tức thì và không có lớp phủ nào.

## Bố cục

- Khoảng cách theo bội số của 4. Gom sát những thứ liên quan, tách rộng các nhóm khác nhau.
- Thẻ có viền mảnh, không kèm bóng. Không lồng thẻ trong thẻ.
- Trang có nhiều phần thì chia thẻ, như trang Cài đặt, thay vì cuộn một danh sách dài.
- Cửa sổ nhỏ thì đổi cấu trúc, không co chữ: bỏ biểu đồ nhỏ, rút gọn nhãn số liệu, ẩn danh sách sự kiện, xếp các khối đôi thành một cột.
- Chữ không đủ chỗ thì bỏ ý cuối hoặc thay bằng dấu ba chấm, không bao giờ để cắt ngang chữ. Ghi chú trong Cài đặt thì xuống dòng.
- Nhãn xuống dòng theo bề rộng khung phải tạo với `elastic=True`: nhãn chỉ xin chiều cao theo số dòng, không xin bề rộng theo chữ. Thiếu cờ này, ở đúng một bề rộng cửa sổ, nhãn và cột chứa nó đẩy nhau qua lại từng điểm ảnh mãi không dừng.

## Những thứ đã bỏ

- Bốn thẻ số liệu giống hệt nhau kèm ô icon: thay bằng một dải số liệu.
- Dải màu dày bên trái mục lịch và dòng đang chọn: màu tag nằm ở nền và chấm tròn.
- Thẻ tiêu đề nhiều màu xếp cạnh nhau cho can chi: thay bằng một dòng chữ.
- Một thẻ trắng lớn bọc cả danh sách, dòng được chọn là hình chữ nhật vuông: thay bằng thẻ việc bo góc.
- Nhóm "7 ngày tới" và chữ "Ngày mai" lặp lại ở mọi dòng: thay bằng nhóm theo từng ngày.
- Segoe UI Variable làm font chính: thay bằng Be Vietnam Pro, đọc rõ hơn ở cỡ nhỏ và dấu tiếng Việt đẹp hơn.
- Thanh cuộn CustomTkinter luôn hiện và cuộn nhảy từng đoạn: thay bằng con trượt mảnh tự ẩn và cuộn mượt.

## Trang Pomodoro

Đồng hồ là thứ duy nhất cần thấy từ xa, nên nó cỡ 72 và đứng một mình giữa thẻ. Dưới nó lần lượt là trạng thái (màu `ACCENT` khi tập trung, `GREEN` khi nghỉ, `MUTED` khi tạm dừng), các chấm của vòng, việc đang gắn, thanh tiến độ và ba nút. Nút chính đổi chữ theo trạng thái: Bắt đầu, Tạm dừng, Tiếp tục. Bộ chọn phiên khoá lại khi đồng hồ đang chạy hoặc tạm dừng, để một cú bấm nhầm không xoá phiên đang dở.

Mặt đồng hồ và thẻ Hôm nay vẽ trên Canvas; mỗi giây chỉ đổi chữ của đồng hồ, thanh tiến độ chỉ vẽ lại khi dài thêm một điểm ảnh. Thời gian còn lại hiện cả trên thanh bên, ở mọi trang, cùng cách làm tròn lên với đồng hồ nổi: vừa bấm 25 phút là `25:00`, chỉ khi hết hẳn giờ mới là `00:00`.

## Câu nói hôm nay

Thẻ cuối cột phải của Tổng quan: dòng nhỏ `Câu nói hôm nay · <chủ đề>` màu `ACCENT`, câu nói trong ngoặc kép cỡ 14 SemiBold, tên tác giả cỡ 13 `MUTED` sau gạch ngang. Cửa sổ thấp thì thẻ này ẩn trước tiên, như câu của ngày ở bản trước.

## Trang Vạn niên

Tờ lịch xếp theo thứ tự người xem cần:

1. Ngày dương, ngày âm, can chi, ngày lễ
2. Đánh giá chung và lý do
3. Hạn trong ngày
4. Nên làm và Kiêng kỵ, mỗi việc ghi rõ căn cứ
5. Giờ, tuổi, hướng
6. Luận ngày, sao tốt và sao xấu
7. Việc của người dùng, câu của ngày, nguồn

Đánh giá chung là phép cộng đơn giản trong `daybook.py`, không phải kết luận của sách nào. Vì vậy app luôn ghi kèm lý do và không hiện điểm số.
