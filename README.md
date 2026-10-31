# TodoLite

Ứng dụng To-Do cá nhân cho Windows 11, ưu tiên hàng đầu là **nhẹ**: khi nghỉ chỉ giữ khoảng 1 MB RAM vật lý và 0% CPU, giao diện chỉ tồn tại khi bạn mở nó. Dữ liệu nằm hoàn toàn trên máy bạn.

- Tự chạy cùng Windows, gửi thông báo tóm tắt việc trong ngày ngay khi đăng nhập
- Dashboard: việc hôm nay, việc quá hạn, tỷ lệ hoàn thành, biểu đồ 7 ngày
- Lịch tuần và lịch tháng: task hiện ngay trên lịch theo màu tag, kéo-thả để dời lịch
- Task chính và checkpoint bên trong, có thanh tiến độ
- Tag có màu: Công việc, Học tập, Gia đình, Cá nhân, Sức khoẻ, Tài chính, và tag tự tạo; mỗi việc gắn được nhiều tag
- Theme tối đen và xanh dương, độ tương phản cao
- Deadline với nhắc trước 5/15/30 phút, 1 giờ, 1 ngày, qua thẻ nhắc có nút Xong, Báo lại, Mở
- Time-blocking: đếm ngược trên Dashboard và đồng hồ nổi góc màn hình
- Thêm nhanh bằng câu tiếng Việt tự nhiên, phím tắt `Ctrl+Alt+T` ở bất kỳ đâu
- Việc lặp lại hằng ngày, T2–T6, hằng tuần, hằng tháng

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

- **Xem:** mỗi việc mang màu tag đầu tiên của nó. Chấm đỏ là quá hạn, chữ gạch ngang là đã xong. Việc lặp lại hiện đủ các lần trong tương lai, với màu nhạt hơn
- **Thêm:** bấm ô trống rồi gõ. Câu được hiểu theo ngày vừa bấm: ở ô thứ Năm, gõ `Họp 14h` là 14:00 thứ Năm. Trên lịch tuần, bấm đúng khung giờ là việc nằm ở giờ đó
- **Dời lịch:** kéo việc sang ngày hoặc giờ khác, khớp theo từng 15 phút; thanh thông báo có nút **Hoàn tác**
- **Đổi thời lượng:** trên lịch tuần, kéo mép dưới của việc. Việc chỉ có hạn chót sẽ thành khối thời gian
- **Cả ngày:** kéo việc lên dải "Cả ngày" hoặc kéo xuống khung giờ để đổi qua lại
- **Lọc:** bấm một tag phía trên lịch để chỉ xem nhóm đó; việc thêm khi đang lọc tự mang tag ấy
- **Xem chi tiết:** bấm vào việc để mở panel bên phải. Ô có quá nhiều việc hiện `+N việc nữa`, bấm để mở tuần đó

Kéo một khối giờ thì hạn chót nằm trong khối sẽ đi theo; hạn chót ở ngày khác đứng yên, nên bạn dời giờ làm mà không vô tình dời deadline.

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

### Phím tắt

| Phím | Tác dụng |
|---|---|
| `Ctrl+Alt+T` | Thêm nhanh ở bất kỳ đâu |
| `Ctrl+N` | Thêm việc mới |
| `Ctrl+F` | Tìm kiếm |
| `Ctrl+1` đến `Ctrl+6` | Tổng quan, Lịch, Hôm nay, Sắp tới, Tất cả, Đã xong |
| `↑` `↓` | Chọn việc trong danh sách |
| `Space` | Hoàn thành việc đang chọn |
| `Esc` | Đóng panel chi tiết |
| `←` `→` | Trên lịch: kỳ trước, kỳ sau |
| `T`, `W`, `M` | Trên lịch: về hôm nay, xem tuần, xem tháng |

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
| Agent đang nghỉ | khoảng 1 MB vật lý (14 MB đã cấp phát) | 0,000% |
| Agent khi có đồng hồ nổi hoặc thẻ nhắc | khoảng 12 MB | rất thấp |
| Giao diện đang mở | khoảng 26 MB, tới 33 MB nếu đã vào mọi trang | dưới 0,6% |
| Mở giao diện từ khay | khoảng 270 ms | |
| Hiện Quick Add | dưới 10 ms | |
| Danh sách 5.000 task | 2,4 ms mỗi bước cuộn | |
| Vẽ lại lịch tháng khi có 3.000 task | khoảng 22 ms | |
| Vẽ lại lịch tuần | khoảng 4 ms | |

Số "khoảng 1 MB" là RAM vật lý thật sự bị chiếm khi agent ngủ; phần còn lại Windows có thể lấy dùng cho việc khác và trả lại khi agent thức. Khi thức, agent tạm dùng khoảng 12 MB.

Vài quyết định giữ app nhẹ:

- Agent trả RAM vật lý về cho hệ thống sau mỗi lần thức (`EmptyWorkingSet`), vì nó sắp ngủ lâu
- Danh sách task vẽ ảo trên một Canvas duy nhất: 5.000 task vẫn chỉ có khoảng 36 đối tượng vẽ
- Quick Add, đồng hồ nổi và thẻ nhắc là cửa sổ Win32 thuần trong agent, nên hiện tức thì mà không cần nạp giao diện
- Toast gọi thẳng WinRT qua ctypes: không cần thư viện toast, mỗi lần chỉ vài chục mili-giây
- Hạ tần suất dò theme và DPI của CustomTkinter từ 33 và 10 lần/giây xuống 1 lần/giây
- Chạy bằng `pythonw.exe` gốc, không qua launcher của venv, để không có thêm một tiến trình thừa

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
├─ assets/                 Icon ứng dụng và khay
├─ tools/setup.py          Logic cài đặt và gỡ cài đặt
├─ vendor/                 Thư viện giao diện, do setup tạo ra
├─ tests/                  Kiểm thử bằng unittest
└─ todolite/
   ├─ cli.py               Phân luồng khởi chạy theo tham số
   ├─ paths.py             Đường dẫn và log siêu nhẹ
   ├─ db.py                SQLite: schema, task, checkpoint, thống kê, sao lưu
   ├─ schedule.py          Logic thời gian thuần: lặp lại, mốc nhắc, chữ hiển thị
   ├─ quickparse.py        Hiểu câu tiếng Việt tự nhiên
   ├─ win32.py             Khai báo Win32 API bằng ctypes
   ├─ toast.py             Toast Windows qua WinRT
   ├─ integration.py       Registry: tự khởi động, đăng ký app
   ├─ agent.py             Tiến trình nền: khay, lịch nhắc, phím tắt
   ├─ popups.py            Quick Add, đồng hồ nổi, thẻ nhắc việc vẽ bằng GDI
   └─ ui/
      ├─ app.py            Cửa sổ chính, điều hướng, nhịp 1 giây
      ├─ pages.py          Trang Tổng quan, danh sách, Cài đặt
      ├─ calendar.py       Lịch tuần và tháng, kéo-thả
      ├─ editor.py         Panel chi tiết task, tự lưu
      ├─ widgets.py        Danh sách ảo, biểu đồ, chọn tag, lịch chọn ngày
      └─ theme.py          Màu sắc, font, icon
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

---

## 8. Kiểm thử

Bộ test chỉ dùng thư viện chuẩn, không đụng tới dữ liệu thật:

```bash
python -m unittest discover -s tests -t .
```

Muốn chạy thử trên dữ liệu riêng, đặt biến môi trường `TODOLITE_DATA` trỏ tới một thư mục khác trước khi mở app. Ở chế độ này app cũng không đụng tới tự khởi động và các đăng ký hệ thống.
