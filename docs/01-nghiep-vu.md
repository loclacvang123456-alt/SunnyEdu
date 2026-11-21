# Quy tắc nghiệp vụ V1

Các mã BR nối yêu cầu với ca nghiệm thu. Giá trị số là mặc định triển khai đã chọn, thay đổi phải cập nhật kiểm thử.

## BR-01. Quyền và lớp

OWNER là giáo viên sở hữu toàn bộ dữ liệu của bản cài đặt. STUDENT chỉ đọc hồ sơ, bài giao và kết quả của mình. Không đăng ký công khai, mạo danh học sinh hoặc tìm tên ở màn hình nhập mã. Trường/khối không tạo quyền. Kiểm tra quyền tại server cho mọi API và tệp, không dựa vào UUID khó đoán.

Học sinh có tên hiển thị và student_ref duy nhất, tên được trùng. Một học sinh có tối đa một lớp trường tại một thời điểm và nhiều lớp tiếng Anh. Chuyển lớp bằng kết thúc membership cũ và mở membership mới, khoảng thời gian [start,end), không sửa lịch sử. Các trạng thái ACTIVE, SUSPENDED, ARCHIVED; hai trạng thái sau chặn đăng nhập và thu hồi phiên, không xóa bài. OWNER có thể khôi phục có log.

## BR-02. Mã và phiên

Mã cá nhân có 20 ký tự ngẫu nhiên Crockford Base32, hiển thị 4 nhóm 5 ký tự. Dùng CSPRNG, bỏ dấu cách/dấu gạch và viết hoa khi nhập; từ chối ký tự ngoài bảng chữ cái. Mã có 100 bit ngẫu nhiên, không lấy từ tên hay mã học sinh. Lưu HMAC-SHA256 với khóa server riêng để tra cứu, chỉ hiển thị mã thô một lần khi cấp. Mã dùng lại đến khi thu hồi; mỗi học sinh tối đa một mã còn hiệu lực. OWNER chỉ cấp lại, không đọc lại mã cũ.

Có thể hiển thị QR cho giáo viên in riêng: URL đăng nhập chứa mã ở fragment, JavaScript đọc, xóa ngay bằng history.replaceState rồi POST. Không đặt mã trong query/path, không lưu QR công khai, không gửi tự động qua dịch vụ khác. Trang đăng nhập không analytics, tài nguyên bên thứ ba hoặc cache. Phải nhắc mã là bí mật và không gửi ảnh QR vào nhóm chung.

Mã lớp ENG-XXXXXX và mã bài HW-XXXXXX ngẫu nhiên, duy nhất, chỉ để mở đúng trang. Chưa xác thực thì không lộ tên lớp/danh sách/nội dung đề. Sau đăng nhập chỉ mở bài thuộc assignment_recipients. V1 không tự vào lớp bằng mã.

Dùng Django database session, đổi session key khi login; không JWT hay lưu token localStorage. Cookie HttpOnly, Secure trên HTTPS, SameSite=Lax, path=/, không domain. Session lưu auth_epoch, issued_at, last_activity và chế độ máy; mỗi request kiểm tra epoch/hạn. Cập nhật last_activity ở mỗi request đã xác thực; dùng timestamp server. Đổi mã/khóa tài khoản tăng auth_epoch, vô hiệu mọi phiên. Logout hủy phiên server và nháp cục bộ của người đó. Database session của Django được bảo vệ bằng quyền DB; không tự thay session engine bằng thuật toán token riêng.

Máy cá nhân: 30 ngày tuyệt đối, idle 14 ngày. Máy chung là mặc định: 2 giờ tuyệt đối, idle 30 phút; đóng trình duyệt không bảo đảm kết thúc phiên. Phiên hết hạn khi đang làm: giữ nội dung trong bộ nhớ trang để nhập mã lại; chỉ đồng bộ nếu đúng chủ nháp. Không tự gửi nháp sang tài khoản khác.

Giới hạn login: 10 lần sai/10 phút theo HMAC mã, 300 request/10 phút/IP và 3.000 request/10 phút toàn ứng dụng. Dùng bảng bucket PostgreSQL cập nhật nguyên tử; 429 + Retry-After, không khóa tài khoản vĩnh viễn. Kiểm thử 100 em cùng IP. Lỗi chung không xác nhận mã có tồn tại; không log mã. IP chỉ là tín hiệu chống lạm dụng.

OWNER dùng password và TOTP qua django-two-factor-auth, bắt buộc cả UI, API và Django admin. Mã phục hồi một lần do thư viện quản lý; hiển thị một lần. Không email reset trong V1. Mất cả TOTP/mã: người vận hành phục hồi qua command có xác minh ngoài hệ thống, log và thu hồi phiên. Phiên OWNER 8 giờ, idle 30 phút; cấp mã, xuất/xóa dữ liệu cần MFA trong 10 phút gần nhất. Rate limit OWNER 5 lần sai/15 phút/tài khoản, thêm giới hạn IP chung. Không tự viết thuật toán TOTP.

## BR-03. Đề

SINGLE_CHOICE và MULTIPLE_CHOICE gắn READING hoặc LISTENING; TEXT gắn WRITING; AUDIO gắn SPEAKING. Không suy kỹ năng nói từ chọn đáp án. Một phiên bản có 1..100 câu, điểm câu 0,01..100,00; SINGLE có 2..6 lựa chọn, đúng 1; MULTIPLE có 2..6, ít nhất 2 đáp án đúng. TEXT tối đa 10.000 ký tự trả lời. AUDIO tối đa 5 phút, 20 MiB. Nội dung thuần text, không HTML do người dùng nhập.

Mỗi câu có đúng một kỹ năng, ít nhất một TOPIC tag; ERROR tag dự kiến tùy chọn. Tài liệu chung gồm đoạn văn và/hoặc audio, nhiều câu trong cùng phiên bản có thể dùng chung. LISTENING bắt buộc tài liệu audio READY, được nghe lại không giới hạn, không tự phát. AUDIO là bài nói do học sinh ghi âm hoặc tải tệp. Tài liệu nghe giáo viên tối đa 10 phút, 30 MiB.

DRAFT được sửa. PUBLISHED bất biến: phải đủ đáp án, tài liệu READY, rubric và tổng điểm >0. Clone thành DRAFT mới, sao chép câu/lựa chọn/rubric/tag và tham chiếu tài liệu bất biến. Tệp đã dùng trong đề PUBLISHED không thay bytes. ARCHIVED ẩn khỏi chọn đề mới nhưng vẫn giữ bài cũ.

Đáp án sai sau khi giao: OWNER hủy assignment có lý do, tạo phiên bản/bài giao thay thế; giữ lịch sử, loại bài hủy khỏi báo cáo. Kỳ xếp hạng có bài hủy thành INVALID; nếu tổ chức lại thì kỳ thay thế phải dùng bài giao mới chưa mở, không dùng lại bộ bài đã làm để lập hạng chính thức. Không sửa đáp án ngầm hoặc chấm lại hàng loạt trong V1.

## BR-04. Bài giao

Assignment có một version, opens_at < due_at, late_policy ALLOW/BLOCK, late_until. Mặc định ALLOW, late_until=due_at+7 ngày. BLOCK đặt late_until=due_at. Nhận bắt đầu/lưu/nộp khi opens_at <= server_now < late_until. Nộp muộn nếu submitted_at > due_at. Quy tắc khoảng nhận là ưu tiên: đúng late_until bị từ chối, kể cả BLOCK. UI ghi rõ hạn đóng, không dùng đồng hồ thi đếm ngược.

Publish chụp danh sách học sinh ACTIVE của các lớp đã chọn vào assignment_recipients, loại trùng. Lưu trường, khối, lớp trường, năm học và tất cả lớp tiếng Anh nhận bài tại thời điểm đó. Vào/rời lớp sau không tự thêm/mất bài. OWNER thêm người nhận hoặc miễn bài có lý do; miễn không xóa lần làm. Không có lớp trường thì lưu null, vẫn làm được, không vào ranking cấp trường/khối.

Sau publish không thay version. Được gia hạn due_at/late_until, không rút ngắn, có lý do và revision; bài đã mở không đổi ALLOW thành BLOCK. is_late được đóng dấu theo hạn lúc nộp, không tính lại quá khứ. Hủy bài ngừng làm/nộp, giữ lịch sử. Bài đã công bố đáp án không gia hạn/cấp lại.

## BR-05. Nháp và nộp

Một người nhận có current_attempt_id và lịch sử. Start tạo IN_PROGRESS trong transaction, gọi lại trả hiện có. Autosave sau 1 giây dừng nhập và khi chuyển câu; trạng thái đang lưu/đã lưu/chưa gửi được. Mỗi request cập nhật một response với expected_revision; server tăng revision. Hai tab sửa cùng câu: request cũ 409, giữ bản tại máy, cho chọn tải bản server hoặc xác nhận ghi đè với revision mới.

Máy cá nhân được lưu text/lựa chọn trong IndexedDB theo user+attempt+question, xóa khi logout hoặc quá 7 ngày. Máy chung chỉ giữ bộ nhớ trang. Không cache audio, đáp án, hồ sơ và feedback offline. Lưu lại sau mất mạng áp dụng thời gian nhận server, không timestamp client. Giáo viên có thể gia hạn khi sự cố. Nháp chưa đồng bộ không bảo đảm phục hồi nếu đóng trang trên máy chung.

Nộp chờ tất cả autosave và audio READY, báo số câu trống rồi cho xác nhận. Request chứa expected_attempt_revision và Idempotency-Key. Transaction khóa attempt, kiểm tra quyền/thời gian/revision/tệp, tự chấm, ghi submitted_at và khóa câu trả lời. Trống được 0 kể cả tự luận, không phải chấm tay; TEXT/AUDIO trống tạo đủ bốn criterion level=0, source=AUTO và feedback “Không có câu trả lời”. AUDIO chỉ trống nếu không gắn asset; asset UPLOADING/REJECTED phải retry hoặc gỡ rõ ràng mới nộp được. Request lặp trả kết quả cũ; nội dung khác với cùng key trả 409.

Trạng thái attempt: IN_PROGRESS, SUBMITTED, GRADED, VOID. SUBMITTED có câu chờ chấm; bài toàn tự động/trống chuyển thẳng GRADED. Quá late_until vẫn IN_PROGRESS nhưng UI “đã hết hạn”, không tự nộp/tính 0. Gia hạn cho phép tiếp tục nháp. VOID do OWNER có lý do, giữ nội dung, không tính báo cáo.

Cấp làm lại tạo attempt mới và đổi current_attempt_id nguyên tử, tối đa 5 lần. Lần cũ phải SUBMITTED/GRADED/VOID; bài còn nhận hoặc đã gia hạn. Không sửa bản cũ. Báo cáo dùng lần mới nên tạm thiếu điểm cho tới công bố, UI cảnh báo trước xác nhận. Cấm làm lại sau công bố đáp án hoặc kỳ ranking liên quan FINAL/STALE. Với bài thuộc kỳ ACTIVE, chỉ cấp lần thay thế do sự cố, lý do bắt buộc; lần cũ VOID. Không cho luyện lặp để lấy điểm hạng cao hơn.

## BR-06. Chấm và công bố

SINGLE đúng được toàn điểm; MULTIPLE đúng khi tập lựa chọn trùng đáp án, không điểm một phần/điểm âm. Decimal, lưu 2 số, ROUND_HALF_UP, không làm tròn lặp khi cộng.

TEXT/AUDIO có 4 tiêu chí cố định, mỗi tiêu chí mức nguyên 0..4. Writing: hoàn thành yêu cầu, tổ chức ý, từ vựng, ngữ pháp. Speaking: nội dung, trôi chảy, từ vựng/ngữ pháp, phát âm dễ hiểu. Các mức: 0 không có bằng chứng đáp ứng, 1 đáp ứng ít, 2 một phần, 3 phần lớn, 4 đầy đủ. Mỗi đề phải có mô tả riêng cho đủ 5 mức của từng tiêu chí trước publish; mẫu mặc định được điền sẵn, giáo viên sửa khi cần. Không quy đổi CEFR.

Điểm câu=max_points×tổng mức/16, làm tròn 2 số. Nhận xét chung và theo tiêu chí, lỗi text có khoảng ký tự, audio có khoảng giây. Trả lời có chữ nhưng lạc đề vẫn cần rubric, không tự coi trống. Không sửa tổng điểm trực tiếp.

Chấm nháp là dữ liệu nội bộ. Publish result chỉ khi attempt còn là current_attempt của recipient chưa miễn và toàn bộ câu đã chấm, tạo GradeRelease bất biến chứa điểm/rubric/feedback/lỗi. Học sinh và báo cáo dùng latest release của current_attempt. Sửa chấm sau công bố phải có lý do; release cũ tiếp tục hiển thị đến khi publish lại, tạo revision mới, không ghi đè. Trước công bố chỉ hiện đã nộp/chờ chấm, không trả điểm trắc nghiệm sớm.

Answers release ở cấp assignment, chỉ sau late_until và không còn current_attempt SUBMITTED của recipient chưa miễn. Không đòi tất cả học sinh nộp. Sau đó cấm gia hạn/cấp lại. Trước answers release, học sinh thấy điểm/nhận xét/lỗi công bố và câu trả lời của mình, không có đáp án đúng/giải thích chuẩn trong HTML/API. Giáo viên có thể tự tiết lộ đáp án trong nhận xét, UI nhắc khi công bố sớm.

## BR-07. Kỹ năng, tiến độ, lỗi

Báo cáo mặc định 28 ngày đến hết hôm nay, lọc theo submitted_at của current_attempt, chỉ latest release, loại bài hủy/miễn/VOID. Điểm kỹ năng=100×tổng điểm câu/tổng max_points. READING/LISTENING cần >=5 câu trong >=2 bài; WRITING/SPEAKING >=2 câu trong >=2 bài để có nhãn. Thiếu mẫu vẫn hiện số liệu và số câu nhưng không gán nhãn; không có dữ liệu không ghi 0.

Mức đạt: <50 cần hỗ trợ, 50..<75 đang củng cố, >=75 đạt tốt. Mức đạt theo khoảng ngày người dùng chọn (mặc định 28 ngày). Xu hướng luôn dùng 28 ngày kết thúc tại ngày to và cửa sổ 28 ngày trước liền kề, độc lập độ dài filter; UI phải ghi rõ hai khoảng so sánh. Trong hai cửa sổ này, chỉ câu cùng difficulty (FOUNDATION/STANDARD/CHALLENGE) và TOPIC có ở cả hai cửa sổ; câu nhiều tag chỉ tính một lần. Cả hai tập sau lọc phải đạt cỡ mẫu. Chênh >=10 điểm phần trăm tăng, <=-10 giảm, còn lại ổn định. Hiển thị mẫu và ghi “theo bài đã làm, độ khó có thể khác”; không kết luận năng lực chuẩn hóa. 90 xuống 60 phải là giảm khi đủ mẫu.

Tiến độ phân biệt chưa bắt đầu, nháp, chờ chấm, chờ công bố, đã công bố, quá hạn chưa nộp, nộp muộn. >=2 bài quá due_at chưa nộp trong 28 ngày thì “cần hỗ trợ tiến độ”. Không dùng thời gian mở trang để gắn nhãn học sinh chậm/yếu.

Tag có kind TOPIC/ERROR, skill và tên. Câu sai chỉ tạo ErrorOccurrence nguồn RULE, trạng thái SIGNAL từ ERROR tag dự kiến; không có tag thì chỉ báo cần ôn câu đó. Giáo viên ghi lỗi nguồn TEACHER, CONFIRMED, với ghi chú sửa và đoạn text/mốc audio. Mỗi response+error tag chỉ một occurrence, sửa cùng lỗi không tăng số lần. Sổ lỗi chính chỉ đếm lỗi trong release mới nhất của current_attempt, loại VOID, bài hủy và recipient miễn. Lỗi của lần cũ vẫn xem trong lịch sử riêng nếu đã công bố; không cộng vào số lần hiện hành. Rút lỗi trong bản chấm chỉ có hiệu lực với học sinh sau republish.

Trang sổ lỗi nhóm theo tag, số lần, lần gần nhất, bằng chứng và cách sửa; học sinh đánh dấu đã xem lại, giáo viên đánh dấu đã kiểm tra lại. Không xóa lịch sử hay tự coi thành thạo. Có thể giao bài luyện mới theo tag, không tự sinh bài hoặc gửi nhắc ngoài ứng dụng.

## BR-08. Xếp hạng

OWNER tạo kỳ có năm học, ngày bắt đầu/kết thúc, scope ENGLISH_CLASS/SCHOOL_CLASS/SCHOOL_GRADE/SCHOOL. Lưu snapshot danh sách học sinh và nhãn lớp/trường; chọn >=1 bài chung. Mọi thành viên phải là recipient không miễn của mọi bài, thiếu thì báo cụ thể, không tự cắt nhóm. Phạm vi trường/khối phải ghi “Học sinh tham gia EDUWEB”, không tuyên bố đại diện toàn trường.

DRAFT sửa được. ACTIVE khóa cohort/bộ bài; chỉ kích hoạt trước opens_at sớm nhất của bộ bài và chưa có attempt được nộp. Các bài phải opens_at >= kỳ start, late_until <= kỳ end. Điểm tạm chỉ OWNER thấy. Mỗi bài một lần, dù giao qua nhiều lớp. Khi tạo kỳ sau một đợt đã làm, chỉ được xem báo cáo điểm, không biến thành ranking chính thức.

Điểm hạng=trung bình phần trăm các bài, trọng số bằng nhau; latest release của current_attempt. Làm tròn cuối 2 số rồi so. Thiếu một bài/còn chờ công bố thì INCOMPLETE không có hạng, không cho 0. Đồng điểm 1,2,2,4. Không phá hòa bằng tốc độ. Nộp muộn vẫn tính điểm, OWNER thấy cờ muộn.

FINAL sau kỳ end, các bài đóng, không còn current_attempt SUBMITTED hoặc GRADED chưa có release trong cohort. Người không nộp/VOID/nháp hết hạn giữ INCOMPLETE. Chốt snapshot gồm nguồn release_id, điểm và hạng, hiển thị số đủ bài/tổng cohort. Chuyển lớp không đổi bảng cũ.

FINAL và STALE đều khóa cohort, bộ bài, hạn và current_attempt. Muốn gia hạn/cấp lại phải chủ động INVALID mọi kỳ liên quan trước, có lý do và cảnh báo mất hạng công bố. Sửa chấm nháp không đổi bảng; publish release mới làm kỳ FINAL thành STALE và ẩn học sinh. Recompute/publish tạo snapshot revision mới, giữ cũ. Bài hủy/miễn recipient thuộc cohort làm kỳ INVALID, tạo kỳ thay thế theo quy trình mới, không tự loại bài để nâng điểm. Không gia hạn bài quá end của kỳ ACTIVE; phải hủy kỳ và lập lịch lại trước khi mở bài, hoặc giữ kỳ INVALID nếu bài đã bắt đầu.

Học sinh mặc định chỉ thấy hạng/điểm của mình khi FINAL. OWNER có thể bật danh sách bí danh riêng kỳ trong lớp tiếng Anh, không tên thật/student_ref/liên kết hồ sơ. Không cam kết ẩn danh tuyệt đối ở lớp nhỏ. Bảng trường/khối/lớp trường chỉ OWNER thấy toàn bảng. Không ai ngoài OWNER xem lỗi hay bài làm của học sinh khác.
