# TodoLite

Ứng dụng To-Do cá nhân cho Windows 11, ưu tiên hàng đầu là **nhẹ**: khi nghỉ chỉ giữ khoảng 1 MB RAM vật lý và 0% CPU, giao diện chỉ tồn tại khi bạn mở nó. Dữ liệu nằm hoàn toàn trên máy bạn.

- Tự chạy cùng Windows, gửi thông báo tóm tắt việc trong ngày ngay khi đăng nhập
- Dashboard: dải số liệu trong ngày, dải 12 giờ âm lịch kèm khối giờ và hạn, việc cần làm, câu nói hôm nay
- Việc quá hạn tô đỏ, việc đã xong tô xanh lá; Tổng quan giữ cả các việc đã xong hôm nay để thấy mình đã làm được gì
- Lịch tuần và lịch tháng: task hiện ngay trên lịch theo màu tag, kéo-thả để dời lịch
- Task chính và checkpoint bên trong, có thanh tiến độ
- Tag có màu: Công việc, Học tập, Gia đình, Cá nhân, Sức khoẻ, Tài chính, và tag tự tạo; mỗi việc gắn được nhiều tag
- Khung xanh đen ở cả hai theme, theme tối đen và xanh dương, độ tương phản cao
- Chữ Be Vietnam Pro đi kèm app, ba mức cỡ chữ, mọi bề mặt bo góc, mỗi việc là một thẻ riêng
- Cuộn mượt bằng con lăn lẫn bàn di chuột laptop, đổi trang mờ dần, theo đúng cài đặt hiệu ứng của Windows
- Deadline với nhắc trước 5/15/30 phút, 1 giờ, 1 ngày, qua thẻ nhắc có nút Xong, Báo lại, Mở
- Time-blocking: đếm ngược trên Dashboard và đồng hồ nổi góc màn hình
- Pomodoro: tập trung 25 phút, nghỉ 5 phút, xong 4 phiên thì nghỉ dài; đồng hồ vẫn chạy khi đóng cửa sổ, đếm số phiên mỗi ngày
- Thêm nhanh bằng câu tiếng Việt tự nhiên, phím tắt `Ctrl+Alt+T` ở bất kỳ đâu
- Việc lặp lại hằng ngày, T2–T6, hằng tuần, hằng tháng
- Bot Telegram dâng tờ tấu mỗi ngày theo năm phần, xưng thần và gọi Bệ hạ, giọng văn đổi theo tình hình thật, API cấu hình được trong Cài đặt
- Thêm việc từ điện thoại: nhắn cho bot như gõ vào ô Thêm nhanh, việc vào app ngay, nhắn `/huy` nếu ghi nhầm
- Bot nhắc trước hạn 15 phút, 30 phút, 1 giờ, 3 giờ, 6 giờ hoặc 1 ngày, và trả lời lệnh `/rp`, `/today`, `/week` bằng số liệu ngay lúc hỏi
- Lịch vạn niên: âm dương lịch, can chi, tiết khí, ngày lễ, đổi ngày âm sang dương
- Xem ngày: đánh giá ngày, hạn trong ngày, việc nên làm và kiêng kỵ kèm căn cứ, giờ, tuổi, hướng xuất hành, sao tốt và sao xấu
- Câu nói hôm nay: 300 câu chia sáu chủ đề, mỗi ngày một câu ngẫu nhiên kèm tên tác giả, chọn chủ đề trong Cài đặt
- Kho thành ngữ, tục ngữ, ca dao và danh ngôn của Vạn niên: mỗi ngày hai câu, ghi rõ nguồn, câu dân gian ghi Khuyết danh
- Hỏi đáp tử vi qua AI theo chuẩn OpenAI, chưa có API key thì luận mẫu ngay trên máy

---

## 1. Cài đặt

**Cần có:** Windows 11, Python 3.10 trở lên từ [python.org](https://www.python.org/downloads/) (đã thử trên 3.15 và 3.11), có mục *tcl/tk and IDLE*.

**Cách nhanh nhất:** nhấp đúp `setup.bat`. Script này không cần quyền admin và làm các việc sau:

1. Kiểm tra Python và tkinter
2. Cài CustomTkinter vào thư mục `vendor/` của dự án, không đụng tới Python hệ thống
3. Đăng ký thông báo với Windows
4. Tạo shortcut trong Start Menu
5. Bật tự khởi động cùng Windows
6. Mở TodoLite

Chạy lại `setup.bat` bất cứ lúc nào, nhất là sau khi nâng cấp Python hoặc chuyển thư mục dự án.

Nếu không muốn tự khởi động:

```bash
py -3 tools\setup.py --no-autostart
```

**Gỡ cài đặt:** nhấp đúp `uninstall.bat`. Dữ liệu task được giữ lại; muốn xoá hẳn, hãy tự xoá thư mục dữ liệu ở mục 6.

---

## 2. Tự khởi động cùng Windows

`setup.bat` ghi một dòng vào registry của người dùng hiện tại:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
TodoLite = "C:\Python315\pythonw.exe" "...\run.pyw" --background
```

Cách này không cần admin và hiện trong **Task Manager → Startup apps**. Windows thường trì hoãn các app khởi động vài giây sau khi đăng nhập, nên thông báo tóm tắt đến ngay sau đó chứ không phải ngay khi màn hình nền vừa hiện.

Có 3 nơi bật/tắt, chọn nơi nào cũng được:

- Trong app: **Cài đặt → Khởi động cùng Windows**
- Chuột phải icon khay → **Khởi động cùng Windows**
- **Task Manager → Startup apps**, mục có tên Python hoặc TodoLite

Thông báo tóm tắt là toast chuẩn của Windows, được gửi ở mỗi lần đăng nhập và lưu trong Notification Center. Nếu PC bật xuyên đêm, app gửi vào giờ đặt trong Cài đặt (mặc định 07:30); khi đang khoá màn hình thì chờ tới lúc mở khoá. Toast chỉ để báo tin: bấm vào nó sẽ đóng toast, muốn mở Dashboard hãy nhấp icon khay.

---

## 3. Sử dụng

### Mở app

- Nhấp icon TodoLite ở khay hệ thống. Windows 11 có thể giấu icon mới trong mũi tên `^`; muốn ghim ra ngoài, vào **Settings → Personalization → Taskbar → Other system tray icons**
- Tìm "TodoLite" trong Start Menu
- Đóng cửa sổ chỉ tắt giao diện; phần nền vẫn chạy để nhắc việc. Muốn thoát hẳn: chuột phải icon khay → **Thoát**

### Danh sách việc

Mỗi việc là một thẻ, bấm vòng tròn để hoàn thành, bấm vào thẻ để xem chi tiết. Thẻ việc quá hạn có nền đỏ nhạt, thẻ việc đã xong có nền xanh lá nhạt. **Sắp tới** chia theo từng ngày trong 14 ngày tới, ví dụ `Ngày mai · Thứ Ba 03/11` rồi `Thứ Tư 04/11`; xa hơn thì chia theo tháng. Tiêu đề nhóm đã có ngày nên dòng việc chỉ ghi giờ, việc cả ngày không ghi gì thêm. Khối thời gian nằm khác ngày với hạn thì ghi kèm ngày, ví dụ `T4 14:00–16:00`.

### Tổng quan

Dải số liệu trên cùng cho biết còn bao nhiêu việc hôm nay, bao nhiêu việc quá hạn (số đỏ) và đã hoàn thành bao nhiêu phần trăm (số xanh lá). Danh sách **Việc cần làm hôm nay** xếp việc quá hạn lên đầu, rồi tới việc của hôm nay, cuối cùng là nhóm **Đã xong hôm nay**: lỡ tay đánh dấu xong thì bấm lại vòng tròn để mở lại.

Thẻ **Câu nói hôm nay** ở cột phải hiện một câu mỗi ngày, kèm chủ đề và tên tác giả. Kho có 300 câu từ tuyển tập *300 câu nói răn dạy làm người*, chia sáu chủ đề: tục ngữ và ca dao Việt Nam; triết lý phương Đông và Phật giáo; nghị lực sống; đối nhân xử thế; trí tuệ, học tập và thời gian; gia đình và hạnh phúc. Câu được xáo ngẫu nhiên, hết một vòng mới lặp lại, và các chủ đề thay phiên nhau nên không có chuyện nhiều ngày liền cùng một chủ đề. Vào **Cài đặt → Chung → Câu nói hôm nay** để tắt những chủ đề không muốn xem. Lời và tên tác giả giữ đúng như tuyển tập, nằm trong `todolite/quotes.py`.

### Cỡ chữ

Vào **Cài đặt → Chung → Cỡ chữ** để chọn **Vừa**, **Lớn** hoặc **Rất lớn**. Chữ và khoảng cách trong toàn bộ cửa sổ phóng to theo, kể cả Quick Add, đồng hồ nổi và thẻ nhắc; đổi là có hiệu lực ngay và được ghi nhớ. Vì cả bố cục lớn lên nên cửa sổ tối thiểu cũng lớn theo, trừ khi màn hình không đủ chỗ.

### Cuộn và chuyển trang

Mọi danh sách và trang dài đều cuộn mượt, bằng con lăn hay bằng hai ngón tay trên bàn di chuột laptop. Mỗi nấc con lăn đi đúng số dòng đặt trong **Settings → Bluetooth & devices → Mouse**. Con trượt mảnh hiện ra khi cuộn, rê chuột tới thì to ra để kéo, bấm vào rãnh thì trượt tới chỗ bấm. Ở Vạn niên, mỗi nấc con lăn hay mỗi lần vuốt lật đúng một tháng.

Đổi trang, đổi tab và mở panel chi tiết thì nội dung mờ dần trong khoảng 160 ms, pill ở thanh bên trượt theo. Muốn tắt mọi hiệu ứng, tắt **Settings → Accessibility → Visual effects → Animation effects** của Windows.

### Thêm việc bằng câu tự nhiên

Gõ vào ô **Thêm việc mới** hoặc bấm `Ctrl+Alt+T` ở bất kỳ đâu. Phần app hiểu được hiện ngay bên dưới trước khi bạn nhấn Enter.

| Bạn gõ | App hiểu |
|---|---|
| `Nộp báo cáo mai 9h !1 #công-việc` | Ngày mai 09:00, ưu tiên cao, nhãn công-việc |
| `Họp t6 14:30` | Thứ Sáu tới, 14:30 |
| `Gọi điện chiều nay` | Hôm nay 15:00 |
| `Trả sách 15/11` | Cả ngày 15/11 |
| `Tắt bếp sau 30p` | 30 phút nữa |
| `Tập gym mỗi t2 18h ~60p` | Thứ Hai 18:00, lặp hằng tuần, khối 60 phút |
| `Uống nước hằng ngày` | Lặp mỗi ngày |

| Cú pháp | Ý nghĩa |
|---|---|
| `hôm nay`, `mai`, `mốt`, `tuần sau`, `cuối tuần`, `cuối tháng` | Ngày |
| `thứ 2`, `t2`, `cn`, `chủ nhật`, `t3 tuần sau` | Thứ trong tuần |
| `15/11`, `15/11/2027`, `ngày 15` | Ngày cụ thể |
| `9h`, `9h30`, `14:00`, `3pm`, `7h tối`, `sáng mai` | Giờ |
| `sau 30p`, `2 tiếng nữa`, `3 ngày nữa` | Tính từ bây giờ |
| `!1` `!2` `!3`, hoặc `!cao` `!vừa` `!thấp` | Ưu tiên |
| `#học-tập`, `#gia-đình` | Tag, gắn được nhiều tag |
| `hằng ngày`, `ngày thường`, `hằng tuần`, `hằng tháng`, `mỗi t2` | Lặp lại |
| `~50p`, `~1h30` | Khối thời gian |

Giờ `1h` đến `6h` không kèm buổi được hiểu là buổi chiều (`họp 2h` là 14:00); muốn giờ sáng hãy ghi `2h sáng` hoặc `02:30`. Gõ không dấu cũng được: `nop bao cao mai 9h`. Tên người như "chị Mai", "Gặp Mai" không bị hiểu nhầm là ngày mai.

### Lịch tuần và tháng

Bấm **Lịch** ở thanh bên, hoặc `Ctrl+2`. Chuyển **Tuần / Tháng** ở góc phải; app nhớ lựa chọn của bạn.

- **Xem:** mỗi việc mang màu tag đầu tiên của nó. Chấm đỏ là quá hạn, chữ gạch ngang là đã xong. Việc lặp lại hiện đủ các lần trong tương lai, với màu nhạt hơn. Số nhỏ cạnh ngày dương là ngày âm, mùng một ghi cả tháng
- **Thêm:** bấm ô trống rồi gõ. Câu được hiểu theo ngày vừa bấm: ở ô thứ Năm, gõ `Họp 14h` là 14:00 thứ Năm. Trên lịch tuần, bấm đúng khung giờ là việc nằm ở giờ đó
- **Dời lịch:** kéo việc sang ngày hoặc giờ khác, khớp theo từng 15 phút; thanh thông báo có nút **Hoàn tác**
- **Đổi thời lượng:** trên lịch tuần, kéo mép dưới của việc. Việc chỉ có hạn chót sẽ thành khối thời gian
- **Cả ngày:** kéo việc lên dải "Cả ngày" hoặc kéo xuống khung giờ để đổi qua lại
- **Lọc:** bấm một tag phía trên lịch để chỉ xem nhóm đó; việc thêm khi đang lọc tự mang tag ấy
- **Xem chi tiết:** bấm vào việc để mở panel bên phải. Ô có quá nhiều việc hiện `+N việc nữa`, bấm để mở tuần đó

Kéo một khối giờ thì hạn chót nằm trong khối sẽ đi theo; hạn chót ở ngày khác đứng yên, nên bạn dời giờ làm mà không vô tình dời deadline.

### Lịch vạn niên

Bấm **Vạn niên** ở thanh bên, hoặc `Ctrl+3`.

- **Lưới tháng:** ngày dương kèm ngày âm. Chấm lục là ngày tốt, tam giác đỏ là ngày xấu, chấm xanh là ngày có việc, chấm vàng là ngày lễ
- **Chuyển ngày:** bấm ô lịch, dùng phím mũi tên, cuộn chuột để đổi tháng, `T` về hôm nay. Gõ năm vào ô cạnh nút **Hôm nay** để nhảy tới năm bất kỳ từ 1800 đến 2199
- **Tờ lịch:** cột bên phải là chi tiết ngày đang chọn, xếp theo thứ tự cần xem. Các mục được giải thích ở phần [Xem ngày](#xem-ngày)
- **Thêm việc:** nút **Thêm việc** hoặc `Ctrl+N` thêm vào ngày đang chọn; gõ `Họp 14h` là 14:00 của chính ngày đó
- **Sự kiện tháng:** bấm một dòng để tới ngày đó
- **Đổi ngày âm sang dương:** nằm dưới lưới tháng, có ô chọn tháng nhuận

Cửa sổ thấp thì danh sách sự kiện tạm ẩn để lưới tháng đủ chỗ, sự kiện vẫn hiện trên tờ lịch.

Lịch được tính bằng thiên văn theo múi giờ UTC+7 và quy tắc lập lịch Việt Nam, không tra bảng, nên đúng cả những năm Việt Nam khác Trung Quốc: Tết 2007 là 17/2, Tết 1985 là 21/1. Vì dùng một quy tắc cho mọi năm, kết quả ở các năm xa, nhất là trước 1968, có thể khác lịch giấy in thời đó.

### Xem ngày

Tờ lịch trả lời ba câu hỏi: ngày có hạn gì, hợp việc gì, kiêng việc gì.

- **Đánh giá chung:** Ngày tốt, Ngày trung bình hoặc Ngày xấu, kèm lý do. Đây là phép cộng đơn giản của app, không phải kết luận của sách nào: hoàng đạo hay hắc đạo, trực, sao nhị thập bát tú và các ngày kỵ. Ngày Đại kỵ và trực Phá luôn là ngày xấu
- **Hạn trong ngày:** các ngày kỵ theo ba mức. **Đại kỵ** là Thụ Tử, Sát Chủ, Dương Công Kỵ Nhật. **Kỵ** là Tam Nương, Nguyệt Kỵ, Nguyệt Tận, Nguyệt Phá, Tứ Ly, Tứ Tuyệt. **Kiêng riêng** là Sát Chủ Dương, Trùng Tang, Trùng Phục, Phục Đoạn, chỉ kỵ vài việc. Nếu đã nhập ngày sinh ở trang Tử vi, app báo thêm khi ngày này kỵ hoặc xung tuổi bạn
- **Nên làm và Kiêng kỵ:** mỗi việc ghi rõ căn cứ, ví dụ *trực Phá, Vãng Vong*. Việc vừa nên vừa kiêng thì xếp vào kiêng. Ngày Đại kỵ không khuyên khởi sự việc gì
- **Giờ trong ngày:** 12 giờ âm lịch, ô xanh là giờ hoàng đạo, ô có viền là giờ hiện tại
- **Tuổi và hướng:** tuổi kỵ, tuổi xung, tuổi hợp, hướng Hỷ Thần, Tài Thần, Hạc Thần, ngày xuất hành theo Khổng Minh
- **Luận ngày:** thần trực, trực, nhị thập bát tú, nạp âm, Bành Tổ bách kỵ
- **Sao trong ngày:** sao tốt và sao xấu theo Ngọc Hạp Thông Thư, mỗi sao kèm lời giải
- **Câu của ngày:** một thành ngữ hoặc cổ ngữ kèm nghĩa, và một câu tục ngữ, ca dao hoặc danh ngôn. Kho này riêng của Vạn niên, khác kho Câu nói hôm nay ở Tổng quan

Việc của bạn trong ngày nằm ngay dưới phần sao, để phân biệt với hạn theo lịch.

Căn cứ của phần này:

- Phan Kế Bính, *Việt Nam phong tục* (1915), chương Xem ngày kén giờ: nguyên tắc tốt xấu và các ngày kỵ
- Tân Việt, Thiều Phong, *Bàn về lịch vạn niên* (1997): bảng sao theo tháng âm, đúc kết từ Ngọc Hạp Thông Thư
- *Hiệp Kỷ Biện Phương Thư*: mười hai trực, Bành Tổ bách kỵ

Lời giải do app viết lại cho ngắn gọn. Các sách và trang lịch không hoàn toàn giống nhau nên kết quả có thể khác đôi chỗ: *Việt Nam phong tục* ghi Dương Công Kỵ Nhật là 12/2 và 8/7, còn TodoLite theo các trang lịch hiện nay và quy luật cách 28 ngày là 11/2 và 1/7. Trực tính theo giờ giao tiết thiên văn nên có thể lệch một ngày so với trang dùng mốc đổi tháng cố định. Kim Thần Thất Sát chưa có vì chưa xác định được quy tắc đủ tin cậy cho mọi năm.

Nội dung để tham khảo văn hoá. Như chính Phan Kế Bính viết, việc thành hay bại cốt do ở người.

### Kho câu của ngày

Có 336 thành ngữ và cổ ngữ kèm lời giải, cùng 399 câu tục ngữ, ca dao và danh ngôn. Hai câu của ngày không lặp lại trong gần một năm. Câu dân gian ghi nguồn là Khuyết danh, câu có tác giả ghi tên người và tác phẩm. Kho được soạn tay từ vốn dân gian phổ biến, tham khảo *Tục ngữ, cổ ngữ, gia ngôn* của Huỳnh Tịnh Của (1897) và trang Tục ngữ Việt Nam trên Wikiquote, đã bỏ các câu thô tục hoặc miệt thị một nhóm người. Trong 692 câu dân gian, 131 câu khớp nguyên văn với hai nguồn đó; các câu còn lại và mọi lời giải chưa được đối chiếu từng câu với sách in, nên có thể khác dị bản bạn từng biết. Danh sách nằm trong `todolite/sayings.py`, sửa trực tiếp được.

### Tử vi

Trong trang Vạn niên, chọn **Tử vi** ở góc phải. Nhập ngày sinh nếu muốn, chọn câu gợi ý hoặc tự gõ câu hỏi. Ngày xem là ngày đang chọn trên lịch; năm sinh được tính theo âm lịch, người sinh trước Tết thuộc năm cũ.

- **Chưa có API key:** app luận mẫu ngay trên máy từ dữ kiện lịch, không gửi gì ra ngoài, và có ghi rõ đây là bản mẫu
- **Có API key:** vào **Cài đặt → Tử vi AI**, dán key. Câu trả lời hiện dần theo thời gian thực, bấm **Dừng** để ngắt. Mặc định dùng DeepSeek với model `deepseek-flash`; đổi API URL và Model là dùng được dịch vụ khác theo chuẩn OpenAI

Khi đã có API key, câu hỏi, dữ kiện lịch và ngày sinh được gửi tới máy chủ AI bạn cấu hình. Nội dung tử vi chỉ để tham khảo.

### Bot Telegram

Mỗi ngày bot dâng một tờ tấu vào Telegram, xưng thần và gọi bạn là Bệ hạ. Tờ tấu có năm phần:

1. **Lời mở:** *Muôn tâu Bệ hạ,* kèm ngay số việc đến hạn và đã trễ, để đọc được từ thông báo trên điện thoại
2. **Báo cáo ngày:** ngày dương, ngày âm, can chi, tiết khí, ngày lễ, đánh giá ngày tốt xấu và lý do
3. **Hạn định:** việc đã trễ, việc đến hạn hôm nay, khối giờ, việc thường nhật và các hạn trong 14 ngày tới
4. **Thuận thiên, kiêng kỵ:** việc nên làm, việc nên kiêng và giờ hoàng đạo, lấy từ phần [Xem ngày](#xem-ngày)
5. **Lời cáo lui:** nêu việc cần Bệ hạ quyết định, chúc long thể an khang, quốc thái dân an

```text
Muôn tâu Bệ hạ, hôm nay có 2 việc đến hạn, 1 việc đã trễ.
Thần kính dâng tờ tấu sớm nay, cúi xin Bệ hạ thánh minh soi xét.

Báo cáo ngày
Thứ Hai, 02/11/2026, tức 24 tháng 9 năm Bính Ngọ.
Ngày Canh Thìn, tháng Mậu Tuất, tiết Sương giáng.
Thần xem sách lịch, hôm nay là ngày xấu: hoàng đạo Thanh Long, trực Phá, sao Tất tốt, phạm Nguyệt Phá.

Hạn định
Đã trễ (1 việc):
• Gửi hợp đồng cho đối tác (trễ 1 ngày)
Hôm nay (2 việc):
• Nộp báo cáo quý 3 lúc 14:00
• Họp nhóm dự án lúc 16:30
Việc thường nhật: uống đủ 2 lít nước.
14 ngày tới (2 việc):
• T4 04/11 lúc 09:00, còn 2 ngày: Ký hợp đồng thuê văn phòng
• T6 13/11, còn 11 ngày: Nộp đề án

Thuận thiên, kiêng kỵ
Việc thuận thiên: chữa bệnh; phá dỡ.
Việc kiêng kỵ: cưới hỏi; khai trương; xuất hành; cầu tài, giao dịch; ký kết; động thổ và 2 việc khác.
Giờ hoàng đạo: Dần 3–5h, Thìn 7–9h, Tỵ 9–11h, Thân 15–17h, Dậu 17–19h, Hợi 21–23h.
Ngu ý của thần, các việc này nên cân nhắc:
• Ký hợp đồng thuê văn phòng ngày 04/11 phạm Sát Chủ, kiêng mọi việc lớn. Ngày gần nhất không vướng là T5 05/11.

Thần xin cáo lui, cúi mong Bệ hạ thánh minh định đoạt: 1 việc đã trễ nên làm ngay hay dời hạn, 1 việc vướng điều kiêng có đổi ngày hay không.
Kính chúc Bệ hạ long thể an khang, quốc thái dân an.
Thần dập đầu kính tấu!
```

Giọng văn đổi theo tình hình thật của ngày, và thay lời mỗi ngày để đọc không chán:

- **Có việc trễ:** lời can gián. Từ 5 việc trễ trở lên, thần liều chết can gián
- **Có việc đến hạn hôm nay:** lời báo khẩn
- **Hạn gần nhất còn tối đa 3 ngày:** tâu trước để Bệ hạ liệu định
- **Không có gì gấp:** lời tụng ca thái bình
- **Ngày lễ và ngày sinh:** lời mừng. Ngày sinh lấy từ trang Tử vi, tính cả ngày dương và ngày âm, gọi là Vạn thọ thánh tiết

Vài điều để tờ tấu dùng được thật:

- Việc lặp hằng ngày hoặc T2–T6 như uống nước, tập thể dục được gom vào dòng **Việc thường nhật**, không tính là trễ hạn. Việc lặp hằng tuần, hằng tháng vẫn là hạn
- Nếu tên việc nói rõ loại việc, như *ký hợp đồng*, *đi công tác*, *lễ cưới*, *khám răng*, và ngày hẹn phạm đúng điều kiêng, bot báo trước và chỉ ra ngày gần nhất không vướng. App chỉ nhận cụm từ rõ nghĩa nên có thể bỏ sót, không tự dời việc nào
- Buổi trong lời tấu theo giờ gửi thật: sớm nay, trưa nay, chiều nay hoặc tối nay
- Danh sách dài được rút gọn, còn tên việc quá dài thì cắt bớt, để tờ tấu luôn nằm trong giới hạn của Telegram và còn đủ lời cáo lui

**Cài đặt lần đầu**, trong **Cài đặt → Telegram**:

1. Nhắn `/newbot` cho [@BotFather](https://t.me/BotFather) để tạo bot, dán token vào ô **Bot Token**
2. Mở bot vừa tạo, nhắn `/start`
3. Bấm **Lấy tự động** để điền Chat ID, hoặc tự nhập nếu gửi vào nhóm hay kênh
4. Bấm **Gửi thử** để xem tờ tấu của hôm nay ngay

Bản tin đi mỗi ngày đúng một lần, theo mốc tới trước: lúc PC bật lần đầu trong ngày, kể cả mở máy lại sau khi ngủ, hoặc giờ đã đặt, mặc định 07:30. Tắt công tắc **Gửi khi PC bật lần đầu trong ngày** thì chỉ gửi đúng giờ. Nếu vừa cài xong mà đã quá giờ, bản tin đầu tiên đi vào ngày mai để app không tự nhắn khi bạn còn đang chỉnh; muốn xem liền thì bấm **Gửi thử**.

Mạng chưa sẵn sàng lúc khởi động thì app tự thử lại nhiều lần. Lỗi cấu hình như sai token thì dừng tới hôm sau, hoặc tới khi bạn sửa, và hiện lý do ngay trong Cài đặt.

Token và API key được mã hoá bằng DPAPI của Windows: file dữ liệu và bản sao lưu có lọt ra ngoài cũng không đọc được, nhưng chuyển sang máy khác thì phải nhập lại. **API URL** cho phép dùng máy chủ riêng hoặc proxy, và bắt buộc `https://`.

### Thêm việc qua Telegram

Nhắn việc cho bot theo đúng cú pháp của [ô Thêm nhanh](#thêm-việc-bằng-câu-tự-nhiên), mỗi dòng là một việc:

```text
Nộp báo cáo mai 9h !1 #công-việc
Tập gym t2 18h hằng tuần
Mua sữa
```

Việc vào app ngay, bot tâu lại phần đã hiểu để bạn soát:

```text
Tâu Bệ hạ, thần đã ghi 3 việc vào sổ:
• Nộp báo cáo (Ngày mai 09:00 · Ưu tiên cao · #Công việc)
• Tập gym (T2 18:00 · Hằng tuần)
• Mua sữa (chưa có hạn)
Lỡ ghi nhầm, Bệ hạ nhắn /huy.
```

| Lệnh | Tác dụng |
|---|---|
| `/rp` | Báo cáo tình hình hôm nay tới lúc này: phần trăm đã xong, việc đã xong, việc còn lại, việc trễ, việc đang làm, Pomodoro, mốc kế tiếp |
| `/today` | Hạn định hôm nay: việc trễ, việc còn hạn hôm nay, khối giờ, việc thường nhật, việc đã xong |
| `/week` | Hạn định 7 ngày tới, xếp theo từng ngày |
| `/huy` | Xoá các việc của tin nhắn vừa ghi |
| `/start`, `/help` | Xem hướng dẫn và ví dụ |

Gõ `/` trong khung chat là Telegram hiện sẵn danh sách lệnh: app đăng ký menu này khi bấm **Kiểm tra bot**, hoặc sau tin nhắn đầu tiên. Mọi con số tính theo lúc bot trả lời, nên nhắn `/rp` giữa trưa là có ngay báo cáo giữa ngày:

```text
Tâu Bệ hạ, tình hình đến 12:05 hôm nay
Đã xong 3/6 việc của hôm nay (50%), còn 2 việc, 1 việc đã trễ.
Đã xong (3 việc):
• Gửi email báo giá (08:40)
• Gọi cho khách (09:15)
• Duyệt hợp đồng (11:30)
Còn lại (2 việc):
• Họp nhóm dự án lúc 15:00 (còn 2 giờ 55 phút)
• Viết báo cáo (cả ngày)
Đã trễ (1 việc):
• Nộp hồ sơ thuế (trễ 1 ngày)
Pomodoro: đang tập trung, còn 12 phút; hôm nay đã xong 4 phiên (1 giờ 40 phút).
Mốc tiếp theo: Họp nhóm dự án, hạn hôm nay 15:00, còn 2 giờ 55 phút.
Thần cúi xin Bệ hạ lo các việc trễ trước.
```

Cần đã cài bot như trên. Tính năng bật sẵn, tắt bằng công tắc **Nhận tin nhắn và lệnh** trong **Cài đặt → Telegram**.

- **PC phải đang bật và TodoLite đang chạy.** PC tắt hoặc ngủ thì tin chờ trên máy chủ Telegram, app đọc khi chạy lại. Telegram chỉ giữ tin 24 giờ, quá thời gian đó tin mất hẳn và app không còn cách lấy lại
- **Ngày giờ tính theo lúc bạn gửi.** Tối nhắn "mai 9h", sáng hôm sau mới bật PC thì việc vẫn hẹn đúng 9 giờ sáng đó
- **Chỉ nhận tin từ đúng Chat ID trong Cài đặt.** Ai cũng nhắn được cho bot, nhưng người lạ không ghi được việc và không nhận được phản hồi nào. Nếu Chat ID là một nhóm, mọi thành viên trong nhóm đều ghi được việc. Kênh thì không dùng được
- Việc không ghi ngày nằm trong **Tất cả**, giống ô Thêm nhanh
- Tin nhắn gửi trước khi bật tính năng không thành việc, để những lần nhắn thử không lẫn vào danh sách. Những tin gửi trong lúc tắt công tắc cũng vậy
- Mỗi tin tối đa 20 dòng, bot báo rõ nếu còn dòng chưa ghi. Tên việc dài quá 200 ký tự thì được cắt, nguyên văn nằm trong ghi chú của việc
- Ảnh có chú thích thì lấy chú thích làm tên việc. Ảnh không chú thích, nhãn dán và tin thoại thì bot báo chỉ đọc được chữ

### Nhắc trước hạn qua Telegram

Trong **Cài đặt → Telegram → Nhắc trước hạn**, chọn một hoặc nhiều mốc: 15 phút, 30 phút, 1 giờ, 3 giờ, 6 giờ, 1 ngày. Mặc định là 1 ngày và 1 giờ; bỏ chọn hết là tắt. Tới mốc, bot nhắn:

```text
Tâu Bệ hạ, còn 1 giờ là tới hạn:
• Nộp báo cáo quý 3, hạn hôm nay 14:00
```

- Chỉ nhắc việc có giờ. Việc cả ngày đã có trong tờ tấu buổi sáng
- Nhắc qua Telegram độc lập với nhắc trên máy (thẻ nhắc ở góc màn hình), hai bên có mốc riêng
- Nhiều việc tới mốc cùng lúc thì gom vào một tin, thời gian còn lại tính theo lúc gửi
- Tin đến điện thoại nên chỉ gửi khi còn đúng lúc. PC tắt hay ngủ qua mốc thì bỏ mốc đó: mốc 1 ngày được gửi trễ tối đa 6 giờ, mốc ngắn tối đa 10 phút, đã qua hạn thì thôi. Vừa tạo việc hạn 20 phút nữa thì không có tin "còn 30 phút". Đổi hạn chót thì các mốc được đặt lại
- Agent tính lịch và chỉ mở một tiến trình ngắn để gửi khi tới mốc; mạng lỗi thì thử lại sau 2 phút

### Tag

Có sẵn 6 tag: Công việc, Học tập, Gia đình, Cá nhân, Sức khoẻ, Tài chính.

- **Gắn tag:** bấm chip màu trong panel chi tiết, hoặc gõ `#học-tập` khi thêm việc. Một việc gắn được nhiều tag
- **Gợi ý khi gõ:** gõ `#` là hiện danh sách tag, nhấn `Tab` để chọn. `#hoc-tap`, `#Học Tập`, `#hoc tap` đều là một tag, không sinh bản trùng
- **Xem theo tag:** bấm tag ở thanh bên
- **Quản lý:** vào **Cài đặt → Tag** để đổi tên, đổi màu (bấm vào chấm màu), tạo mới hoặc xoá. Xoá tag không xoá việc

### Checkpoint

Bấm vào một việc để mở panel chi tiết. Gõ checkpoint rồi Enter để thêm liên tiếp, tích để hoàn thành, nhấp đúp để đổi tên. Tiến độ hiện ngay trên dòng task và trong thông báo.

### Deadline và nhắc nhở

Ô **Hạn chót** nhận câu tự nhiên, có thêm lịch và nút nhanh. Chọn các mốc nhắc trước hạn ngay bên dưới. Việc chỉ có ngày (không có giờ) không có nhắc riêng; chúng nằm trong tóm tắt buổi sáng. Thay đổi deadline sẽ tự đặt lại các mốc nhắc.

Tới giờ nhắc, một thẻ hiện ở góc phải màn hình, kèm tiếng báo:

- **Xong:** hoàn thành việc ngay tại thẻ
- **Báo lại 10 phút:** thẻ quay lại sau 10 phút
- **Mở:** mở đúng việc đó trong app
- Nút `X` đóng thẻ mà không đổi gì

Thẻ ở lại cho tới khi bạn xử lý, nên rời máy một lúc cũng không lỡ, và thời gian trên thẻ luôn tính lại theo thực tế. Nhiều nhắc cùng lúc thì xếp hàng lần lượt; từ 4 nhắc trở lên được gộp thành một thông báo. Khi đang chiếu slide hoặc chơi game toàn màn hình, app không bật thẻ đè lên mà gửi toast thay thế. Nếu máy tắt hoặc ngủ quá 12 giờ, các nhắc cũ được bỏ qua và việc quá hạn sẽ nằm trong tóm tắt.

### Time-blocking

- Trên Dashboard: chọn một việc rồi bấm 25, 50 hoặc 90 phút để bắt đầu đếm ngược
- Trong panel chi tiết: đặt giờ bắt đầu trước, ví dụ `14h` hoặc `mai 9h`
- Khi khối chạy, đồng hồ nổi hiện ở góc màn hình kể cả đã đóng Dashboard. Kéo để di chuyển, nhấp đúp để mở app, chuột phải để thêm 5 phút, kết thúc hoặc ẩn
- Hết giờ, thẻ nhắc hỏi bạn đã xong hay cần thêm 10 phút

### Pomodoro

Bấm **Pomodoro** ở thanh bên, hoặc `Ctrl+4`.

- **Bắt đầu, Tạm dừng, Tiếp tục:** nút lớn dưới đồng hồ. **Bỏ qua** chuyển sang phiên kế mà không tính phiên đang dở, **Đặt lại** quay về phiên tập trung đầu vòng
- **Vòng Pomodoro:** tập trung 25 phút, nghỉ ngắn 5 phút; xong 4 phiên tập trung thì nghỉ dài 15 phút. Các chấm dưới đồng hồ là số phiên đã xong trong vòng
- **Chọn việc:** bấm một việc trong danh sách để gắn với Pomodoro, bấm lại để bỏ gắn. Phiên xong được tính cho việc đó
- **Thời lượng:** chỉnh bằng nút bớt, thêm trong thẻ Thời lượng. Mặc định giờ nghỉ tự bắt đầu ngay khi hết phiên tập trung, còn phiên tập trung chờ bạn bấm
- **Đóng cửa sổ vẫn chạy:** hết phiên thì Windows báo, đồng hồ nổi ở góc màn hình đếm ngược (nhấp đúp để mở trang Pomodoro, chuột phải để tạm dừng, bỏ qua, dừng), thanh bên hiện thời gian còn lại ở mọi trang
- **Thống kê:** thẻ Hôm nay đếm số phiên, tổng thời gian tập trung và biểu đồ 7 ngày; lệnh `/rp` của bot cũng báo Pomodoro

Đồng hồ chạy theo giờ thật chứ không đếm từng giây, nên máy ngủ giữa phiên cũng không lệch: thức dậy là phiên đã hết được ghi lại ngay.

### Phím tắt

| Phím | Tác dụng |
|---|---|
| `Ctrl+Alt+T` | Thêm nhanh ở bất kỳ đâu |
| `Ctrl+N` | Thêm việc mới |
| `Ctrl+F` | Tìm kiếm |
| `Ctrl+1` đến `Ctrl+8` | Tổng quan, Lịch, Vạn niên, Pomodoro, Hôm nay, Sắp tới, Tất cả, Đã xong |
| `↑` `↓` | Chọn việc trong danh sách |
| `Space` | Hoàn thành việc đang chọn |
| `Esc` | Đóng panel chi tiết |
| `←` `→` | Trên lịch: kỳ trước, kỳ sau |
| `T`, `W`, `M` | Trên lịch: về hôm nay, xem tuần, xem tháng |
| `←` `→` `↑` `↓` | Trên Vạn niên: chuyển ngày, chuyển tuần |

Bấm trực tiếp vào các thẻ số trên Tổng quan để mở danh sách tương ứng.

---

## 4. Vì sao chọn công nghệ này

**Python + ctypes cho tiến trình nền, CustomTkinter cho giao diện, SQLite cho dữ liệu.**

Điểm mấu chốt không phải là chọn thư viện giao diện nào, mà là **tách đôi tiến trình**. Bảng dưới là số đo trên chính máy phát triển (Windows 11 26H2, Python 3.15.2), với cửa sổ mẫu 20 dòng, lấy trung vị của 3 lần:

| Phương án | RAM riêng (cột Memory của Task Manager) | Working set | Thời gian mở | Dung lượng thư viện |
|---|---:|---:|---:|---:|
| Win32 thuần qua ctypes (không giao diện) | 5,7 MB | 17,5 MB | 50 ms | 0 |
| tkinter | 12,2 MB | 36,1 MB | 167 ms | 0 |
| CustomTkinter | 20,8 MB | 49,0 MB | 331 ms | khoảng 3 MB |
| PySide6 | 21,1 MB | 64,9 MB | 311 ms | trên 170 MB |

PySide6 thực ra không tốn RAM hơn CustomTkinter là bao, nhưng nặng đĩa gấp hàng chục lần. CustomTkinter thắng ở chỗ gọn và đủ đẹp. Dù vậy, app nào giữ giao diện chạy nền suốt ngày cũng tốn trên 20 MB, nên TodoLite chia làm hai:

- **Agent nền:** chỉ dùng thư viện chuẩn và Win32 API. Nằm yên trong vòng lặp thông điệp, thức dậy đúng lúc có việc thay vì quét định kỳ
- **Giao diện:** tiến trình riêng, chỉ sống khi cửa sổ mở. Đóng cửa sổ là trả toàn bộ RAM cho hệ thống

Số đo của app thật:

| Trạng thái | RAM | CPU |
|---|---:|---:|
| Agent đang nghỉ | khoảng 0,9 MB vật lý (9 MB đã cấp phát) | 0,000% |
| Agent đang nghe tin nhắn Telegram | khoảng 1,1 MB vật lý, thêm 0,5 MB đã cấp phát | khoảng 2 ms CPU mỗi phút |
| Agent khi có đồng hồ nổi hoặc thẻ nhắc | khoảng 12 MB | rất thấp |
| Giao diện đang mở | khoảng 27 MB, tới 40 MB nếu đã vào mọi trang | đứng yên: khoảng 0,1% ở Tổng quan (đồng hồ đếm ngược), dưới 0,1% ở trang khác |
| Trang Pomodoro khi đồng hồ chạy | thêm khoảng 1,8 MB khi mở lần đầu | khoảng 50 ms CPU mỗi phút, tức 0,09% |
| Giao diện thu nhỏ xuống thanh tác vụ | khoảng 1,6 MB | gần 0%, khoảng 1 lần thức mỗi giây |
| Số cửa sổ Tk | 60 khi mở Tổng quan, khoảng 740 khi đã vào mọi trang | |
| Chuyển trang | dưới 25 ms | |
| Kéo giãn cửa sổ | khoảng 4 ms mỗi bước | |
| Gửi bản tin Telegram | tiến trình riêng, sống vài giây rồi thoát | |
| Gửi nhắc hạn, trả lời `/rp`, ghi việc từ tin nhắn | tiến trình riêng 60–85 ms, đỉnh khoảng 22 MB rồi thoát | |
| Mở giao diện từ khay | khoảng 330 ms, trong đó nạp thư viện khoảng 75 ms | |
| Mở lần đầu trang Lịch, Vạn niên, Tử vi | 100–150 ms | |
| Mở lần đầu trang Pomodoro | khoảng 210 ms | |
| Mở lần đầu panel chi tiết, Cài đặt | 270–285 ms | |
| Hiện Quick Add | dưới 10 ms, lần đầu sau khi agent khởi động khoảng 50 ms vì phải nạp font | |
| Danh sách 5.000 task | khoảng 1 ms mỗi khung hình khi cuộn | |
| Chuyển cảnh mờ dần | chụp vùng nội dung 1,7 ms, mỗi khung dưới 0,1 ms | |
| Vẽ lại lịch tháng khi có 3.000 task | khoảng 33 ms | |
| Vẽ lại lịch tuần khi có 3.000 task | khoảng 43 ms | |

Số "khoảng 0,9 MB" là RAM vật lý thật sự bị chiếm khi agent ngủ; phần còn lại Windows có thể lấy dùng cho việc khác và trả lại khi agent thức. Khi thức, agent tạm dùng khoảng 12 MB.

Vài quyết định giữ app nhẹ:

- Agent trả RAM vật lý về cho hệ thống sau mỗi lần thức (`EmptyWorkingSet`), vì nó sắp ngủ lâu. Khi nghe Telegram, việc trả RAM được hẹn 1,5 giây sau lúc bắt đầu mỗi lượt chờ: ở chế độ đồng bộ WinHTTP chỉ trả về khi máy chủ đã trả lời, nên trả RAM ngay lúc gửi là trả khi luồng còn đang dựng kết nối, nó chạm lại vài MB và giữ suốt 50 giây
- Danh sách task vẽ ảo trên một Canvas duy nhất: 5.000 task vẫn chỉ có khoảng 100 đối tượng vẽ
- Quick Add, đồng hồ nổi và thẻ nhắc là cửa sổ Win32 thuần trong agent, nên hiện tức thì mà không cần nạp giao diện. Font Be Vietnam Pro chỉ được nạp khi popup đầu tiên hiện, ngày không có popup thì agent không tốn gì
- Thanh bên vẽ trên một Canvas duy nhất, thay cho 159 cửa sổ Tk: mỗi mục CustomTkinter là cả một cụm khung, canvas và nhãn
- Chữ tĩnh dùng nhãn Tk một cửa sổ thay cho CTkLabel (ba cửa sổ), vẫn theo theme, cỡ chữ và màu nền của khung cha. Dải số liệu và chip bật tắt tự vẽ trên một Canvas, giữ nguyên cỡ và vị trí chữ như widget CustomTkinter cũ. Tổng số cửa sổ khi mở Tổng quan giảm từ 303 xuống 60, khi đã vào mọi trang từ 1.085 xuống khoảng 650
- Góc bo khử răng cưa là bốn ảnh nhỏ tính sẵn và giữ lại theo màu, phần thân là một hình chữ nhật, nên vẽ bao nhiêu hình cũng chỉ tốn vài ảnh. Polygon của Tk không có khử răng cưa
- Rê chuột hay chọn việc trên danh sách chỉ vẽ lại đúng hai dòng vừa đổi
- Cuộn danh sách giữ nguyên các dòng đã vẽ và chỉ dời chúng đi, dòng lọt vào khung mới được vẽ, dòng ra khỏi khung bị xoá
- Mọi chuyển động dùng chung một vòng khung hình, vòng này chỉ chạy khi có thứ đang chuyển động và tắt hẳn khi đứng yên. Chỉ trong lúc đó app mới xin bộ hẹn giờ 1 ms của Windows, vì bộ hẹn giờ mặc định 15,6 ms làm khung hình lúc 16 ms lúc 31 ms
- Chuyển cảnh chụp từ chính cửa sổ của app (dưới 2 ms, chụp màn hình mất hơn 11 ms) rồi chỉ đổi độ mờ của một cửa sổ lớp, nên gần như không tốn gì
- Con trượt vẽ ngay trên Canvas thay cho thanh cuộn CustomTkinter, vốn bắt Tk dàn lại bố cục ở mỗi lần đặt vị trí
- Toast gọi thẳng WinRT qua ctypes: không cần thư viện toast, mỗi lần chỉ vài chục mili-giây
- CustomTkinter tự dò theme và DPI mỗi giây suốt đời cửa sổ. TodoLite chỉ dò theme khi đang chọn theme theo hệ thống (2 giây một lần), còn DPI thì dò khi cửa sổ chuyển màn hình và 5 giây một lần
- CTkTextbox dò xem có cần thanh cuộn 5 lần mỗi giây kể cả khi đã tắt thanh cuộn: ô chữ của TodoLite bỏ vòng dò này
- Nhịp mỗi giây chỉ chạy khi cửa sổ đang hiện, dừng hẳn khi thu nhỏ, và chỉ vẽ lại thanh tiến độ khi nó dịch đủ một điểm ảnh. Thu nhỏ xong giao diện chỉ thức khoảng 1 lần mỗi giây
- Không nạp `packaging` (11 ms) mà CustomTkinter chỉ dùng để so phiên bản Python, không liệt kê cả 300 font của máy khi font đi kèm đã nạp được, thanh thông báo chỉ dựng khi cần lần đầu
- Bỏ cờ `CS_HREDRAW` và `CS_VREDRAW` của lớp cửa sổ Tk, và giữ nguyên bố cục trong lúc kéo giãn: thả tay mới sắp xếp lại một lần
- Khung xếp chỗ trong suốt không có canvas riêng, tab Cài đặt và các trang chỉ dựng khi mở lần đầu
- Chạy bằng `pythonw.exe` gốc, không qua launcher của venv, để không có thêm một tiến trình thừa
- Bản tin Telegram được gửi bởi một tiến trình riêng, nên lỗi mạng không làm nghẽn nhắc việc. Nhắc trước hạn qua Telegram cũng vậy: agent chỉ tính mốc và hẹn giờ thức, tới mốc mới mở một tiến trình ngắn để gửi
- Đồng hồ Pomodoro không đếm từng giây ở đâu cả: database giữ giờ hết phiên, agent hẹn đúng một lần thức vào lúc đó, giao diện chỉ đổi chữ của đồng hồ mỗi giây khi đang mở. Không dùng Pomodoro thì agent không nạp module của nó
- Nhãn tự xuống dòng theo bề rộng khung (câu nói hôm nay, ghi chú trong Cài đặt) không xin bề rộng theo chữ. Nếu xin, ở đúng một bề rộng cửa sổ chữ xin rộng thêm 1 điểm ảnh làm cột co lại, chữ xuống thêm một dòng nên xin hẹp đi, cột nở ra, cứ thế lặp vô hạn và treo cửa sổ. Bản 1.5 có lỗi này ở thẻ Tập trung; bản 2.0 đã sửa và được quét ở từng bề rộng từ 960 đến 1.500 điểm ảnh
- Chủ đề câu nói chọn bằng chip vẽ trên Canvas thay vì sáu dòng công tắc: Cài đặt bớt khoảng 45 cửa sổ Tk và mở nhanh hơn khoảng 40 ms
- Phần mạng gọi thẳng WinHTTP của Windows thay vì `urllib` và `ssl`: không nạp OpenSSL, tự dùng proxy và kho chứng chỉ của hệ thống
- Nghe tin nhắn Telegram bằng một luồng nằm chờ trong WinHTTP: máy chủ giữ kết nối tới 50 giây và trả lời ngay khi có tin, nên luồng ngủ trong hệ điều hành thay vì thức dậy dò hỏi. Có tin mới mở một tiến trình ngắn để đọc, ghi việc rồi thoát, agent không phải nạp `json` hay phần hiểu tiếng Việt

**Vì sao nhắc việc dùng thẻ riêng thay vì nút trên toast?** Nút trên toast của app không đóng gói phải gọi về app qua một URI tuỳ chỉnh, và trên Windows 11 26H2 việc này bật hộp thoại "chọn ứng dụng để mở" ngay cả khi đã đăng ký đầy đủ. Thẻ do chính agent vẽ thì bấm là xử lý ngay trong tiến trình, không cần đăng ký gì thêm và không cướp focus của cửa sổ bạn đang làm việc. Toast vẫn được dùng cho tin chỉ cần đọc, như tóm tắt đầu ngày.

**Theme đen và xanh dương.** Bảng màu dựa trên GitHub Dark High Contrast và Tokyo Night: nền gần như đen, chỉ một màu xanh để nhấn, nên phần quan trọng nổi bật mà app vẫn tối giản. Độ tương phản được tính theo công thức WCAG chứ không chọn bằng mắt:

| Cặp màu (theme tối) | Tương phản | Mức WCAG cần |
|---:|---:|---:|
| Chữ chính trên thẻ | 17,3:1 | 4,5:1 |
| Chữ phụ trên thẻ | 9,4:1 | 4,5:1 |
| Xanh nhấn trên thẻ | 8,6:1 | 4,5:1 |
| Chữ trắng trên nút xanh | 4,6:1 | 4,5:1 |
| Chữ trên nền màu tag | từ 9,4:1 | 4,5:1 |

**Cách làm lịch** tham khảo các app nhiều người dùng: TickTick (tô màu theo tag, kéo-thả đổi giờ, kéo mép đổi thời lượng), Super Productivity (23,3k sao GitHub, xem ngày làm việc theo dòng thời gian) và Vikunja (5,9k sao GitHub).

Hai tính năng chọn lọc từ các app lớn:

- **Quick Add bằng ngôn ngữ tự nhiên (Todoist):** tiết kiệm thời gian nhiều nhất, hoàn toàn là logic nên gần như không tốn tài nguyên. TodoLite hiểu tiếng Việt, có hoặc không dấu
- **Việc lặp lại (TickTick, Todoist):** hoàn thành một lần là tự sinh lần kế tiếp, checkpoint đặt lại từ đầu

---

## 5. Cấu trúc dự án

```text
app local/
├─ run.pyw                 Điểm vào duy nhất, nhấp đúp để mở
├─ setup.bat               Cài đặt một chạm
├─ uninstall.bat           Gỡ khỏi Windows, giữ dữ liệu
├─ requirements.txt        Chỉ có customtkinter
├─ DESIGN.md               Quy tắc thiết kế giao diện
├─ PRODUCT.md              Người dùng và ràng buộc của sản phẩm
├─ assets/                 Icon ứng dụng và khay, font Be Vietnam Pro kèm giấy phép OFL
├─ tools/setup.py          Logic cài đặt và gỡ cài đặt
├─ vendor/                 Thư viện giao diện, do setup tạo ra
├─ tests/                  Kiểm thử bằng unittest
└─ todolite/
   ├─ cli.py               Phân luồng khởi chạy theo tham số
   ├─ paths.py             Đường dẫn và log siêu nhẹ
   ├─ db.py                SQLite: schema, task, checkpoint, thống kê, sao lưu
   ├─ schedule.py          Logic thời gian thuần: lặp lại, mốc nhắc, chữ hiển thị
   ├─ easing.py            Phép tính chuyển động: cuộn mượt, đường cong, nấc con lăn và bàn di chuột
   ├─ quickparse.py        Hiểu câu tiếng Việt tự nhiên
   ├─ win32.py             Khai báo Win32 API bằng ctypes
   ├─ toast.py             Toast Windows qua WinRT
   ├─ integration.py       Registry: tự khởi động, đăng ký app
   ├─ agent.py             Tiến trình nền: khay, lịch nhắc, phím tắt
   ├─ popups.py            Quick Add, đồng hồ nổi, thẻ nhắc việc vẽ bằng GDI
   ├─ lunar.py             Âm lịch: đổi ngày, can chi, tiết khí, ngày và giờ hoàng đạo
   ├─ almanac.py           Ngày lễ dương lịch, âm lịch
   ├─ daybook.py           Xem ngày: trực, sao, ngày kỵ, nên làm và kiêng kỵ
   ├─ sayings.py           Kho thành ngữ, tục ngữ, ca dao, danh ngôn của Vạn niên
   ├─ quotes.py            Kho Câu nói hôm nay: 300 câu, sáu chủ đề, chọn câu mỗi ngày
   ├─ pomodoro.py          Đồng hồ Pomodoro: trạng thái, chuyển phiên, ghi phiên đã xong
   ├─ telegram.py          Bot Telegram: soạn tờ tấu, gửi, thử lại
   ├─ report.py            Tờ tấu theo lệnh /rp, /today, /week
   ├─ remind.py            Nhắc trước hạn qua Telegram
   ├─ bot.py               Gọi Bot API của Telegram
   ├─ listener.py          Luồng nghe tin nhắn trong agent
   ├─ inbox.py             Đọc tin nhắn, ghi việc, tâu lại
   ├─ ai.py                Tử vi: lời nhắc, gọi AI, bản luận mẫu
   ├─ web.py               Gọi mạng qua WinHTTP của Windows
   ├─ vault.py             Mã hoá token và API key bằng DPAPI
   └─ ui/
      ├─ app.py            Cửa sổ chính, điều hướng, nhịp 1 giây
      ├─ pages.py          Trang Tổng quan, danh sách, Cài đặt
      ├─ calendar.py       Lịch tuần và tháng, kéo-thả
      ├─ almanac_page.py   Trang Vạn niên và Tử vi
      ├─ pomodoro_page.py  Trang Pomodoro
      ├─ editor.py         Panel chi tiết task, tự lưu
      ├─ sidebar.py        Thanh bên vẽ trên một Canvas
      ├─ motion.py         Vòng khung hình, cuộn mượt, con trượt, chuyển cảnh mờ dần
      ├─ widgets.py        Danh sách ảo, dải 12 giờ, biểu đồ, chọn tag, lịch chọn ngày
      ├─ shapes.py         Hình bo góc khử răng cưa trên Canvas
      └─ theme.py          Màu sắc, bán kính bo góc, font, icon
```

Hai tiến trình dùng chung một file SQLite ở chế độ WAL nên không khoá nhau. Giao diện báo "dữ liệu đổi" cho agent bằng một `PostMessage`; ngược lại, giao diện nhận ra thay đổi từ agent qua `PRAGMA data_version`.

---

## 6. Dữ liệu

| Nội dung | Vị trí |
|---|---|
| Dữ liệu | `%LOCALAPPDATA%\TodoLite\todo.db` |
| Sao lưu tự động | `%LOCALAPPDATA%\TodoLite\backups\`, mỗi ngày một bản, giữ 7 bản gần nhất |
| Sao lưu trước nâng cấp | `backups\before-schema-N.db`, tạo tự động trước khi đổi cấu trúc dữ liệu |
| Nhật ký lỗi | `%LOCALAPPDATA%\TodoLite\app.log` |
| Bot Token, API key | Trong `todo.db`, đã mã hoá bằng DPAPI theo tài khoản Windows |

**Khôi phục từ bản sao lưu:** thoát app, chép bản muốn dùng trong `backups\` đè lên `todo.db`, xoá `todo.db-wal` và `todo.db-shm` nếu có, rồi mở lại. Vào **Cài đặt → Mở thư mục** để tới nhanh.

---

## 7. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy thông báo | **Cài đặt → Gửi thử**. Nếu vẫn không có, kiểm tra **Settings → System → Notifications** và chế độ Do not disturb |
| Bấm vào toast không mở app | Đúng như thiết kế, toast chỉ báo tin. Nhấp icon khay để mở |
| Không thấy icon khay | Bấm mũi tên `^` trên taskbar, hoặc ghim như ở mục 3 |
| `Ctrl+Alt+T` không hoạt động | Một ứng dụng khác đang chiếm phím; xem `app.log` |
| Không tự khởi động sau khi đổi Python hoặc chuyển thư mục | Chạy lại `setup.bat` |
| App không mở được | Xem `app.log`, hoặc chạy `python run.pyw --ui` trong terminal để thấy lỗi |
| Không nhận được bản tin Telegram | Xem dòng trạng thái cuối thẻ **Cài đặt → Telegram**, rồi bấm **Kiểm tra bot** và **Gửi thử** |
| `Lấy tự động` báo chưa thấy tin nhắn | Nhắn `/start` cho bot ngay trước khi bấm, hoặc tự nhập Chat ID |
| Bot báo đang dùng webhook | Bot đang nối với chương trình khác, hãy tự nhập Chat ID |
| Nhắn cho bot mà không thấy việc | Kiểm tra PC đang bật, TodoLite đang chạy, công tắc **Nhận tin nhắn và lệnh** đang bật, rồi xem dòng trạng thái cuối thẻ **Cài đặt → Telegram** |
| Không nhận được nhắc trước hạn | Việc phải có giờ (không phải cả ngày) và có mốc được chọn trong **Cài đặt → Telegram → Nhắc trước hạn**; PC phải đang bật lúc tới mốc |
| Gõ `/` trong Telegram không thấy lệnh | Bấm **Kiểm tra bot** trong **Cài đặt → Telegram** để đăng ký lại menu lệnh |
| Pomodoro không báo khi hết phiên | Kiểm tra **Settings → System → Notifications** của Windows; đồng hồ vẫn chuyển phiên đúng giờ |
| Báo bot đang dùng webhook hoặc chương trình khác đang đọc tin | Mỗi bot chỉ được một nơi đọc tin. Tắt chương trình kia, hoặc tạo bot riêng cho TodoLite |
| Đổi tài khoản Telegram mà `Lấy tự động` không thấy tin | Xoá trống ô **Chat ID**, nhắn `/start` từ tài khoản mới, rồi bấm **Lấy tự động** |
| Tử vi báo sai model | Dịch vụ AI đã đổi tên model; sửa ô **Model** theo tài liệu của dịch vụ |
| Cuộn nhảy cóc, đổi trang không mờ dần | **Animation effects** của Windows đang tắt, app làm theo cài đặt đó |
| Không thu nhỏ cửa sổ được như trước | **Cỡ chữ** Lớn và Rất lớn phóng to cả bố cục nên cửa sổ tối thiểu cũng lớn theo; chọn lại **Vừa** |
| Token mất tác dụng sau khi đổi máy hoặc tài khoản Windows | DPAPI gắn với tài khoản Windows, hãy nhập lại |

---

## 8. Kiểm thử

Bộ test chỉ dùng thư viện chuẩn, không đụng tới dữ liệu thật và không gọi mạng ra ngoài: Telegram và AI được thử trên máy chủ giả chạy cục bộ.

```bash
python -m unittest discover -s tests -t .
```

Âm lịch được đối chiếu với dữ liệu độc lập: 72.684 ngày từ 1901 đến 2099 so với bảng lịch Trung Quốc của thư viện `lunardate`, và các ngày công bố trên baohatinh.vn, xemlicham.com, ngaydep.com. Chênh lệch với bảng Trung Quốc đến từ múi giờ UTC+7 so với UTC+8, đúng như các trường hợp đã biết là Tết 2007 và Tết 1985. Bài kiểm tra chỉ dùng để phát triển nên `lunardate` không nằm trong `requirements.txt`.

Phần xem ngày được đối chiếu như sau: 28 sao khớp hoàn toàn 73.019 ngày từ 1900 đến 2100 với thư viện `lunar-python`, trực lệch 0,14% ở các ngày giao tiết sát nửa đêm do UTC+7 so với UTC+8. Bảng sao tốt xấu khớp 415 ngày liên tiếp và 146 ngày ngẫu nhiên từ 2000 đến 2035 trên xemlicham.com, trừ vài ngày lỗi của trang đó. Ba sao Thiên Xá, Âm Thác, Dương Thác được tính đúng theo can chi của sách, nên khác trang đó ở những ngày trang chỉ khớp một nửa can chi. Một phần dữ liệu đối chiếu nằm trong `tests/data`.

Muốn chạy thử trên dữ liệu riêng, đặt biến môi trường `TODOLITE_DATA` trỏ tới một thư mục khác trước khi mở app. Ở chế độ này app cũng không đụng tới tự khởi động và các đăng ký hệ thống.
