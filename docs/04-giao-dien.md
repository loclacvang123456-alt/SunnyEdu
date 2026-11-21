# Giao diện và hành vi

Đặc tả này là bố cục để agent dựng UI, không phải ảnh mockup đã kiểm chứng. V1 dùng light theme; không thêm dark mode, avatar tải lên hoặc hiệu ứng game gây phân tâm. Trang làm bài dùng nội dung thật từ server, không điểm/số liệu giả ngoài demo fixtures.

## Hệ thiết kế

| Token | Giá trị |
|---|---|
| background / surface | #F8FAFC / #FFFFFF |
| text / muted | #0F172A / #475569 |
| primary / on-primary | #2563EB / #FFFFFF |
| success / success-bg | #166534 / #DCFCE7 |
| warning / warning-bg | #9A3412 / #FFEDD5 |
| danger / danger-bg | #B91C1C / #FEE2E2 |
| border / focus | #CBD5E1 / #1D4ED8 |
| font | system-ui, Segoe UI, Arial, sans-serif; không tải font bên thứ ba |
| font sizes | 14 chú thích, 16 nội dung/form, 20 tiêu đề thẻ, 28 tiêu đề trang, 36 chỉ ở welcome desktop |
| line-height | Nội dung 1.6, tiêu đề 1.25 |
| spacing | 4, 8, 12, 16, 24, 32, 48 px |
| radius | Input/button 10px; thẻ học sinh 16px, bảng/form giáo viên 8px |
| control | Chiều cao tối thiểu 44px, vùng chạm 44×44 CSS px, khoảng nút >=8px |

Dùng CSS custom properties, không rải màu hex trong component. Tương phản chữ thường mục tiêu >=4.5:1, focus và điều khiển có ý nghĩa >=3:1; kiểm tra cặp thực tế khi dựng. Hover/pressed/focus/disabled/error phải riêng biệt; không chỉ dùng màu để báo đúng/sai. Icon SVG cùng một bộ có nhãn chữ; không dùng emoji làm nút. Học sinh có hình trang trí SVG đơn giản về sách/tai nghe/bút trên trang chủ và hoàn tất, không đặt giữa câu hỏi.

Chuyển trạng thái màu/opacity 120–180ms, không đổi bố cục; tắt chuyển động theo prefers-reduced-motion. Không nhấp nháy, âm thanh chúc mừng tự phát, streak ép học liên tục hoặc bảng xếp hạng đỏ những em cuối.

## Điều hướng và responsive

Student: Bài của em, Kết quả, Em cần ôn, Hồ sơ. Ranking nằm trong Kết quả, không thêm mục chính. Header có tên đang dùng và Đăng xuất rõ để tránh nhầm tài khoản. Desktop nav ngang, mobile thanh cuối trang với bốn nhãn, trừ màn hình làm bài dùng thanh điều khiển riêng.

Owner: Tổng quan, Học sinh & lớp, Đề, Bài giao, Chấm bài, Báo cáo, Cài đặt. Sidebar desktop 240px, mobile drawer có nút mở/đóng và quản lý focus. Breadcrumb cho đề → phiên bản → câu hỏi. Tìm kiếm theo tên/mã và giữ bộ lọc trong URL, không đưa bí mật vào URL.

Breakpoints: <768 một cột với lề 16px; 768..1023 hai cột khi phù hợp, lề 24px; >=1024 sidebar owner và nội dung tối đa 1280px. Trang làm bài tối đa 1100px; câu chữ dài tối đa khoảng 75 ký tự một dòng. Không cuộn ngang toàn trang; bảng owner được cuộn riêng có nhãn hoặc chuyển sang thẻ. Kiểm tra 360,390,768,1280px, landscape và zoom 200%. Thanh cố định chừa padding và safe-area, không che focus/bàn phím điện thoại.

## S00. Trang chủ Sunny Edu

Khách chưa đăng nhập vào `/` thấy trang chủ Sunny Edu với banner và slider, giới thiệu bốn kỹ năng, cách học bằng mã và đường dẫn vào học. Slider có nút trước/sau và chọn nội dung, dùng được bằng bàn phím; mặc định không tự chạy. Số học sinh là số tài khoản học sinh ACTIVE trong hệ thống, hiển thị cả khi bằng 0; không dùng số liệu tự đặt. Dữ liệu mẫu chỉ để thử local. Nút “Vào học” dẫn tới `/login/`, đường dẫn giáo viên đến `/teacher/login/`. Học sinh đã có phiên hợp lệ vào `/` được chuyển đến trang bài tập; giáo viên đã đăng nhập theo luồng xác thực giáo viên.

Logo sẽ được tạo bằng Gemini theo yêu cầu: chữ SUNNY EDU in hoa nét dày uốn quanh một đường tròn, sáu tia dùng các chữ A, B, C, A, B, C kéo hẹp. Trong thời gian chờ logo, giao diện chỉ hiển thị tên Sunny Edu. Prompt chi tiết nằm trong `chi-tiet-hinh-anh-website-tieng-anh.md`.

## S01. Vào học

Thẻ giữa trang: tên EDUWEB, “Nhập mã của em”, input có label, nút hiện/ẩn mã, checkbox “Đây là máy của em” mặc định tắt, nút “Vào học”. Cho paste và quét QR bằng camera của thiết bị qua liên kết, không bắt nhập từng ô ký tự. Dưới form: “Quên mã? Nhờ thầy/cô cấp lại.” Liên kết giáo viên nhỏ và riêng.

Sai mã: “Mã chưa đúng hoặc đã được đổi. Em kiểm tra lại hoặc nhờ thầy/cô.” 429 hiển thị thời gian thử lại, giữ input trong trang nhưng không ghi log. Không tự lộ danh sách học sinh để lựa tên. Login xong trở lại bài deep-link nếu được phép; nếu không hiện không truy cập được và nút về Bài của em.

## S02. Bài của em

Header tên học sinh và lớp; danh sách bài ưu tiên chưa làm gần hạn, rồi đang làm, chờ chấm, đã công bố. Mỗi thẻ: tên, kỹ năng bằng chữ/icon, hạn nộp, trạng thái, một nút chính “Làm bài” hoặc “Làm tiếp”. Bài chưa mở hiện ngày mở và nút disabled có giải thích. Quá hạn nhưng còn nhận hiện “Có thể nộp muộn đến ...”. Bài chờ chấm không ghi 0 điểm.

Empty: “Em chưa có bài được giao.” Lỗi tải có nút thử lại, không hiển thị empty thay lỗi. Không đưa bảng kỹ năng/xếp hạng lên trước nhiệm vụ cần làm.

## S03. Làm bài

Desktop:

```text
[Quay lại] Tên bài                         Tên học sinh
Hạn nộp ...                         Đã lưu lúc ...
[Đoạn đọc / trình nghe: 40%] [Câu hỏi và trả lời: 60%]
[Danh sách số câu: đã làm / còn trống bằng icon + chữ]
[Câu trước] [Câu tiếp]                           [Nộp bài]
```

Mobile: tài liệu nghe/đọc ở trên, có “Thu gọn tài liệu”; câu và đáp án dưới. Giữ vị trí nghe khi chuyển câu dùng chung tài liệu, không tự reset audio. Chuyển câu không tải lại toàn trang. Các lựa chọn là radio/checkbox native trong vùng nhấn rộng; nhấn cả dòng chọn, vẫn có focus. TEXT có label, đếm ký tự và không giới hạn mất chữ âm thầm.

AUDIO: “Ghi âm”, timer, “Dừng”, nghe lại, “Ghi lại”, hoặc “Tải bản ghi”. Chỉ hỏi quyền micro khi nhấn Ghi âm. MediaRecorder chọn MIME theo isTypeSupported, không giả định webm trên Safari. Hết 5 phút dừng và giữ bản nghe lại, không tự nộp. Từ chối micro thì hướng dẫn quyền hoặc tải file. Tải file có tiến độ/Thử lại/Gỡ; bản lỗi không tự thành câu bỏ trống. Không đóng trang khi bản ghi chưa được gửi mà không cảnh báo.

Nút Nộp mở dialog: số câu chưa trả lời, trạng thái audio, “Sau khi nộp em không sửa bài này được”, Hủy/Xác nhận nộp. Trong request disable nút, nếu timeout cho thử lại cùng idempotency key. Chỉ trang xác nhận từ server mới ghi “Đã nộp lúc ...”; không dùng animation thành công để thay receipt.

Mất mạng: banner “Chưa gửi được thay đổi. Em giữ trang này mở.” Hiện rõ câu chưa lưu. Conflict 409: dialog bản trên máy/bản trên server, chọn giữ một bản, không tự hợp nhất text. Phiên hết hạn: form đăng nhập lại giữ nội dung trang; đăng nhập khác học sinh yêu cầu bỏ nháp của người cũ, không chuyển bài.

## S04. Kết quả và sổ lỗi

Kết quả: tổng điểm release, thời điểm công bố, bốn thanh ngang kỹ năng có điểm và số câu/bài, mức đạt và xu hướng nằm ở hai dòng riêng. Không vẽ radar mặc định vì dễ tạo ấn tượng cân bằng giả khi thiếu kỹ năng. Thiếu mẫu dùng dấu gạch và giải thích, không thanh 0. Có bộ lọc thời gian, lịch sử lần làm và nhãn “lần hiện tại”.

Chi tiết câu: câu trả lời của em, điểm, rubric, nhận xét; đoạn lỗi gạch chân có text label và nút mở cách sửa. Không chỉ tô đỏ. Audio lỗi có nút nghe từ giây được ghi; không phát tự động. Đáp án chuẩn chỉ có sau release riêng.

Sổ lỗi: nhóm theo kỹ năng/tag, hiện số lần và ví dụ gần nhất, nhãn “cần ôn” cho RULE và “giáo viên ghi nhận” cho TEACHER. Nút “Em đã xem lại” cập nhật review, không xóa thẻ hay hiển thị đã thành thạo. Xếp hạng: hạng của em, điểm, số đủ bài/tổng nhóm, quy tắc; chưa đủ bài nêu bài còn thiếu. Không hiển thị bảng STALE/INVALID như mới nhất.

## T01. Tổng quan và lớp

Tổng quan owner hiển thị số bài cần chấm, học sinh quá hạn, bài đang mở; mỗi số dẫn đến danh sách đã lọc. Không tính cả bài được miễn vào quá hạn. Học sinh & lớp có tab lớp tiếng Anh và trường/khối/lớp trường, tránh dùng một ô “lớp” cho hai nghĩa.

Hồ sơ học sinh: tên/mã nội bộ, memberships, bài và tiến độ, kỹ năng, sổ lỗi, lịch sử đổi mã/khóa. Cấp mã cần MFA mới, dialog hiển thị mã/QR một lần và nhắc gửi riêng. Chuyển lớp cho xem “Các bài và báo cáo cũ vẫn giữ lớp tại thời điểm giao”. Archive có xác nhận, không dùng nút Xóa cho nghỉ học.

## T02. Đề và nhập

Danh sách đề có title, version, trạng thái, kỹ năng, số câu. Editor: panel câu bên trái, form nội dung/loại/kỹ năng/difficulty/tài liệu/đáp án/điểm/topic/error/rubric bên phải. Các control không áp dụng được ẩn theo loại và xóa chỉ sau xác nhận nếu có dữ liệu. Có nút xem trước như học sinh, không làm rò đáp án sang tài khoản học sinh.

Import gồm chọn loại + file + title, preview bảng dòng hợp lệ/lỗi/tag mới, nút nhập chỉ bật khi không lỗi. Commit xong đến đề DRAFT; không tự publish. Đề PUBLISHED là read-only và có “Tạo bản sửa”. Publish hiển thị tổng câu/điểm, kỹ năng thiếu và lỗi cản phát hành, focus tới lỗi đầu.

## T03. Giao và chấm

Form giao: phiên bản, lớp nhận, danh sách học sinh sau loại trùng, mở/hạn/đóng, cho nộp muộn. Preview có số người nhận và trường hợp chưa có lớp trường. Sau publish, nút gia hạn/miễn/thêm người nhận/cấp lại có lý do và cảnh báo ảnh hưởng ranking.

Màn hình chấm desktop hai cột: bài học sinh và audio/text bên trái, rubric/nhận xét/tag lỗi bên phải. Mobile xếp dọc; rubric không cuộn ngang. Lưu nháp và Công bố là hai nút khác nhau; thiếu tiêu chí không công bố. Có trạng thái lưu, phiên bản điểm và cảnh báo khi attempt đã bị thay thế. Sửa kết quả đã công bố cho xem điểm cũ/mới và bắt lý do. Công bố đáp án nằm ở trang bài giao, không nằm cạnh nút lưu điểm từng em.

## T04. Báo cáo và kỳ xếp hạng

Bộ lọc từ rộng đến hẹp: năm học, trường, khối, lớp trường, lớp tiếng Anh, khoảng ngày. Thay trường reset khối/lớp không còn phù hợp. Báo cáo có bảng dữ liệu bên cạnh thanh kỹ năng, xuất đúng filter hiện hành. Chủ đề/lỗi và tiến độ hiển thị riêng; không tự tạo một điểm tổng năng lực bốn kỹ năng khi thiếu dữ liệu.

Tạo kỳ dùng wizard: phạm vi/cohort → bộ bài chung → thời gian và kiểm tra → kích hoạt. Hiện số học sinh thiếu quyền nhận bài, ngày chưa hợp lệ, không cho tự bỏ các em khỏi nhóm. Chốt kỳ hiển thị số đủ bài, chờ chấm, thiếu bài. STALE có banner cần công bố lại; INVALID ghi lý do và giữ lịch sử. Không có sửa cohort hoặc bộ bài sau ACTIVE.

## Kiểm tra giao diện

Mọi input có label, lỗi cạnh field và summary có link; dialog có focus trap, Escape và trả focus. Tab/Enter/Space dùng được; lựa chọn có fieldset/legend; thông báo lưu dùng aria-live polite, không đọc mọi ký tự. Không tắt zoom/paste. Button không hoạt động phải có lý do gần đó. Giữ filter và vị trí khi quay lại. Màn hình dữ liệu cần đủ loading/empty/error/forbidden/expired; không dùng toast tự mất cho lỗi có nguy cơ mất bài.
