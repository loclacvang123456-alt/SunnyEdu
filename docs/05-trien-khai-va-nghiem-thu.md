# Triển khai, vận hành và nghiệm thu

## 1. Cấu trúc ứng dụng

Python 3.13, Django 5.2 bản vá mới nhất tương thích lúc khởi tạo, psycopg 3, PostgreSQL 17 bản vá được hỗ trợ. HTML templates Django, CSS tokens, JavaScript ES modules thuần cho autosave/recording/dialog; không cần React hoặc Node build. Dependency dự kiến: django-two-factor-auth cho MFA, openpyxl+defusedxml cho XLSX, boto3 cho S3, gunicorn trên Linux. Chọn phiên bản còn được hỗ trợ, kiểm tra tương thích và khóa chính xác trong lock file; không tự đổi framework. Phần nguồn đã đối chiếu ở tài liệu gốc.

```text
config/                 settings local/test/production, urls, wsgi
apps/accounts/          users, code login, session, MFA và rate limit
apps/classes/           trường, lớp và membership
apps/content/           đề, version, câu, rubric, import
apps/assignments/       recipients, attempt, autosave, submit
apps/grading/           grade, errors, result release
apps/reporting/         kỹ năng, tiến độ, ranking, export
apps/core/              audit, assets, privacy, health, cron commands
templates/              student, owner, shared
static/                 css tokens/components, js modules, svg
tests/                 unit, PostgreSQL integration, browser, load
 docs/                  đặc tả này, OpenAPI, deployment runbook, test reports
```

Mỗi app có models, services, selectors/queries và views. Views kiểm tra input/quyền, services chứa transaction và quy tắc; không đưa logic chấm vào JavaScript hoặc template. Không abstraction dùng chung nếu chỉ có một nơi sử dụng. Django admin chỉ hỗ trợ tra cứu; chặn chỉnh trực tiếp các model có invariant, không tạo cửa hậu sửa điểm/đề/session.

Local dùng Docker Compose cho PostgreSQL và kho S3 tương thích; app có thể chạy trong container hoặc Python local. Tài nguyên giả lập, không lấy dữ liệu thật. `seed_demo` chỉ chạy khi DEBUG/local, tạo OWNER và mã demo rõ ràng, không tài khoản/password mặc định trong production. Agent phải cung cấp README với lệnh setup, migrate, seed_demo, run, test và cách đăng nhập local đã kiểm chứng.

Không dùng cache CDN cho trang đăng nhập, bài, kết quả, audio hoặc API cá nhân. Static CSS/JS được cache bằng tên có hash. Không service worker trong V1. Tác vụ dọn dữ liệu chạy cron mỗi giờ; không Celery/Redis. Báo cáo <=1.000 học sinh chạy đồng bộ, query có giới hạn và index; không cần background queue trước khi đo tải cho thấy cần.

## 2. Triển khai production

Một container Django sau reverse proxy HTTPS, PostgreSQL managed kết nối private nếu có, S3-compatible bucket private cùng vùng gần ứng dụng, cron container dùng cùng image. Nhà cung cấp và vùng do chủ dự án chọn trước khi vận hành; local không phụ thuộc tài khoản cloud. Có môi trường staging riêng bằng dữ liệu giả, bucket/database/secret tách production.

Biến cấu hình bắt buộc: DATABASE_URL, DJANGO_SECRET_KEY, ACCESS_CODE_HMAC_KEYS theo version, RATE_LIMIT_HMAC_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, S3_ENDPOINT_URL, S3_BUCKET, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, PUBLIC_BASE_URL, ENVIRONMENT, PRIVACY_NOTICE_VERSION. Không đưa secret vào Git, image, ví dụ README hoặc frontend; .env.example chỉ tên và placeholder. Chính sách quyền bucket cấp đúng prefix/app cần dùng, không quyền quản lý account cloud.

Build image có dependency khóa, quét dependency có lỗi nghiêm trọng, chạy test trước khi release. Thực hiện migration một process trước web mới, backup trước thay đổi dữ liệu. Migration nên tương thích app cũ/mới trong lúc chuyển; không rollback schema mù quáng. Rollback image chỉ khi schema tương thích, nếu không dùng sửa tiến hoặc phục hồi đã diễn tập. Health: /health/live không DB, /health/ready kiểm tra DB và migration, trả status chung không version/secret. Không kiểm tra S3 bằng ghi mới ở mỗi health request; dùng kiểm tra định kỳ.

## 3. Bảo mật và dữ liệu trẻ em

Quyền mặc định từ chối. Kiểm tra test A không đọc/sửa assignment, response, grade, asset, error hoặc ranking của B. OWNER có MFA và tái xác thực thao tác nhạy cảm. Bật Django CSRF/template escaping, HTTPS, HSTS sau khi xác nhận HTTPS toàn site, secure cookies, ALLOWED_HOSTS cụ thể, CSP self-only với nonce khi cần; không script nội tuyến tùy ý, không user HTML, không iframe ngoài. Cache-Control: no-store cho nội dung cá nhân. Không trả secret/answer key trong HTML data attributes, JSON, log, source map hoặc payload lỗi.

Tệp audio nhận qua backend streaming, không đọc toàn bộ vào RAM. Cho phép MP3, M4A/MP4 audio, WebM audio, Ogg audio; từ chối HTML/SVG/ZIP/executable và video track. Xác minh chữ ký file, MIME thực tế, số stream, thời lượng bằng ffprobe cập nhật trong process giới hạn CPU/RAM, timeout 10 giây, tham số argv không shell, chỉ tệp local và không network. Học sinh <=20 MiB/5 phút, giáo viên <=30 MiB/10 phút. Reverse proxy cap request 35 MiB, app kiểm tra giới hạn riêng. Không tin extension hoặc Content-Type client. Không public phục vụ file chưa READY.

Không transcode V1: thử phát định dạng ghi âm trên Chrome Android và Safari iOS thật, nếu không tương thích thì báo đổi/tải MP3/M4A; không báo upload thành công nếu asset bị REJECTED. Content-Type dùng detected MIME, nosniff, tên download do server chuẩn hóa. Asset proxy hỗ trợ Range, kiểm tra quyền mỗi lần, dừng khi revoke; xử lý storage outage với lỗi có thể retry. Upload chưa gắn hết hạn sau 24 giờ, cron xóa object rác; cleanup khóa asset trong transaction, kiểm tra không có reference rồi đổi DELETING. Attach bị cấm từ lúc đó. Sau commit mới xóa object, thành công đổi DELETED; lỗi giữ DELETING cho retry idempotent, không báo đã xóa.

Rate limit upload 10 request/10 phút/student, tối đa 2 upload đồng thời/student; response save 120 request/phút/student, ngưỡng đủ cho autosave; trước nộp chờ request đang lưu. Hạn mức pilot: tổng audio 20 GiB, cảnh báo OWNER ở 80%, ở 100% chặn upload mới với giải thích và cho giáo viên gia hạn; không âm thầm mất file. Hạn mức là cấu hình vận hành, cần theo dõi thực tế trước mở rộng.

Thu thập tên/mã/lớp và bài làm, không thu vị trí, danh bạ, camera hoặc ngày sinh. Ghi âm chỉ xin micro khi học sinh nhấn. Không quảng cáo, tracking bên thứ ba hay dùng bài làm huấn luyện AI. Trước dùng dữ liệu thật, chủ dự án phải cung cấp thông báo cho học sinh/phụ huynh, người liên hệ, mục đích, thời gian lưu, cách yêu cầu xuất/xóa và căn cứ xử lý phù hợp. Tài liệu kỹ thuật này không chứng nhận đáp ứng mọi nghĩa vụ pháp lý; không tự tạo tuyên bố “đã tuân thủ”.

Retention mặc định: dữ liệu học tập giữ đến 24 tháng sau khi học sinh rời tất cả lớp; OWNER nhận danh sách tới hạn và có 30 ngày xác nhận xóa hoặc ghi lý do gia hạn. Log kỹ thuật giữ 30 ngày, audit metadata 12 tháng; không log request body. Login bucket chỉ giữ 24 giờ. Import preview 24 giờ, nháp offline 7 ngày. Bản sao lưu DB/audio giữ tối đa 35 ngày. Các giá trị có thể điều chỉnh trước production theo yêu cầu đã xác minh, không tùy tiện trong UI học sinh.

Xuất dữ liệu: OWNER xác nhận MFA, tạo JSON/CSV của đúng một học sinh cùng danh sách tài nguyên được phép, không token/mã/password; tải qua phiên xác thực, no-store, không link public. Yêu cầu xóa: PrivacyRequest có phê duyệt OWNER, khóa user/thu hồi phiên, xóa nội dung bài/audio/error/grade/release cá nhân, xóa hoặc thay thông tin nhận dạng trong audit và snapshot; kỳ ranking liên quan thành INVALID. Giữ tombstone không chứa tên cho mục đích chống phục hồi nhầm. Job idempotent, báo số bản ghi/tệp còn lỗi và chỉ COMPLETED khi dọn active data xong. Snapshot JSON phải được xử lý, không chỉ xóa User. Audio dùng chung của đề không xóa nhầm.

Sổ yêu cầu xóa/tombstone phải có bản lưu ngoài bộ backup phục hồi chính, chỉ người vận hành đọc. Backup hết hạn trong 35 ngày; nếu khôi phục trước đó phải áp dụng lại yêu cầu xóa phát sinh sau bản backup trước khi mở traffic. Không hứa xóa ngay mọi bản backup nếu chưa có quy trình thực hiện.

## 4. Sao lưu và giám sát

Mục tiêu pilot RPO <=24 giờ, RTO <=4 giờ, phải đo khi diễn tập, không coi là SLA đã đạt. Backup DB mỗi ngày, object versioning/lifecycle 35 ngày hoặc bản sao tương đương; mã hóa và giới hạn người đọc. Dữ liệu đang dùng cần tồn tại độc lập với image/container. Giám sát backup thành công và khả năng đọc thử, không chỉ tồn tại file.

Mỗi tháng diễn tập restore staging: lấy backup, khôi phục DB/tệp, đối chiếu số recipient/attempt/release và checksum audio mẫu, áp dụng tombstone mới, đăng nhập thử, đọc bài/kết quả/audio, ghi thời gian/RPO thực tế. Nếu thiếu tệp không báo restore thành công. Credential backup tách credential web, không lưu khóa giải mã cùng backup.

Theo dõi: 5xx, p95 latency, DB connections/storage, upload lỗi, kho sắp đầy, số đăng nhập sai, cron/backup thất bại. Cảnh báo nếu 5xx >1% trong 5 phút có >=100 request, backup >26 giờ chưa thành công, disk >80%. Kênh cảnh báo của chủ dự án cấu hình khi deploy; agent không tự gửi tin cho người khác. Incident mã lộ: revoke code+epoch; owner account lộ: khóa truy cập, rotate secret phù hợp, phục hồi MFA và kiểm tra audit. Không ghi mã vào báo cáo sự cố.

## 5. Các giai đoạn cho agent

| Mốc | Công việc và điều kiện kết thúc |
|---|---|
| M0 | Khởi tạo repo/app, settings/compose, migrations, CI local, README, fixtures giả. Check migration từ DB rỗng, chạy test PostgreSQL. |
| M1 | OWNER+MFA, học sinh/lớp/memberships, login code/session/rate limit. Đạt AC01..AC05. |
| M2 | Đề/version/rubric/tag/audio/import preview-commit, giao bài và snapshot recipients. Đạt AC06..AC10. |
| M3 | Trang làm bài, autosave/revision/offline, audio, nộp idempotent, chấm trắc nghiệm. Đạt AC11..AC17. |
| M4 | Rubric, chấm nháp, công bố, chỉnh điểm, sổ lỗi và báo cáo. Đạt AC18..AC23. |
| M5 | Ranking lifecycle/snapshot/privacy/export. Đạt AC24..AC29. |
| M6 | UI responsive/a11y, kiểm thử tải, hardening, backup/restore, runbook và xử lý dữ liệu. Đạt AC30..AC35. |

Mỗi mốc ghi file đổi, test đã chạy, lỗi còn lại và cách chạy lại. Không kết thúc V1 sau M3. Không để TODO ở đường đi login/nộp/chấm/permission hoặc dùng fake data cho phần chưa xây. Khi có lỗi test phải sửa nguyên nhân, không giảm assertion để qua.

## 6. Tiêu chí nghiệm thu

| ID | Tình huống và kết quả bắt buộc |
|---|---|
| AC01 | Login mã đúng vào đúng học sinh; mã sai/hết hiệu lực phản hồi chung; không tìm danh tính qua tên hoặc mã lớp. |
| AC02 | Đổi mã làm mã cũ và hai phiên thiết bị cũ hết quyền ngay ở request tiếp theo; mã mới vào được. |
| AC03 | Hai em cùng IP vẫn vào đúng tài khoản; 100 login hợp lệ trong 10 phút cùng IP không bị chặn; vượt từng bucket nhận 429, Retry-After. |
| AC04 | Máy chung hết 2 giờ/idle 30 phút; máy cá nhân hết 30 ngày/idle 14 ngày; dùng clock cố định để test; logout xóa nháp cục bộ. |
| AC05 | STUDENT truy cập UI/API/asset của người khác bị từ chối; OWNER chưa TOTP không vào API/admin; thiếu CSRF không thay dữ liệu, gồm PUT autosave và PUT grade. |
| AC06 | Câu MULTIPLE đáp án A,C: A,C được toàn điểm; A/C/A,B,C hoặc rỗng 0; SINGLE chọn option câu khác 422. |
| AC07 | Publish thiếu đáp án/rubric/topic/listening audio bị chặn; PUBLISHED không sửa được qua UI, API hoặc admin; clone tạo bản mới. |
| AC08 | Import mẫu thành công; dòng lỗi làm cả batch không commit; retry commit không nhân đôi; XLSX công thức/ZIP quá giới hạn bị từ chối. |
| AC09 | Giao cùng bài qua hai lớp có cùng học sinh chỉ tạo một recipient; chuyển lớp sau đó không đổi quyền hoặc snapshot cũ. |
| AC10 | Thêm học sinh vào lớp không tự nhận bài cũ; OWNER thêm recipient rõ ràng mới thấy bài; miễn giữ lịch sử và loại tiến độ. |
| AC11 | Autosave lần đầu tăng revisions; tab cũ sửa cùng câu nhận 409 và không mất bản mới; nộp revision cũ bị chặn. |
| AC12 | Mất mạng giữ text đúng chế độ máy; gửi sau late_until bị từ chối; không hiển thị đã nộp nếu server chưa xác nhận. |
| AC13 | Nộp hai request đồng thời/cùng key chỉ có một lần chấm, cùng receipt; retry sau hạn vẫn nhận receipt; key cũ payload khác 409. |
| AC14 | Server khóa nhận tại đúng late_until; ALLOW nộp giữa due_at và late_until là muộn; BLOCK không nhận từ due_at. |
| AC15 | AUDIO đang upload/rejected không thể nộp âm thầm; gỡ file rõ ràng mới thành trống; file quá 5 phút/20 MiB bị từ chối. |
| AC16 | Đáp án đúng, explanation và transcript không có trong student HTML/JSON trước answers release; request trực tiếp cũng bị chặn. |
| AC17 | Cấp lại giữ bản cũ, đổi current attempt; publish đồng thời bản cũ bị chặn, không sửa báo cáo chính thức. Cấm retake khi đáp án đã mở hoặc kỳ FINAL/STALE. |
| AC18 | Câu max=10, rubric 3,2,4,3 cho 7.50; thiếu một tiêu chí không publish; sửa tổng trực tiếp bị từ chối. |
| AC19 | Bài có câu trống TEXT/AUDIO được AUTO grade 0 với đủ 4 tiêu chí 0; audio đã gắn nhưng lỗi không coi là trống. |
| AC20 | Chấm nháp không lộ điểm; publish mới hiện; sửa nháp sau publish vẫn hiện release cũ, republish có revision/lý do mới. |
| AC21 | Một kỹ năng các câu 2/4 và 3/6 cho 50%; không trung bình 2 tỷ lệ theo số bài. Không có câu thì thiếu dữ liệu, không 0. |
| AC22 | Hai cửa sổ đủ mẫu cùng topic/difficulty: 90 xuống 60 là xu hướng giảm và mức đang củng cố; khác topic hoặc thiếu mẫu thì không gán xu hướng. Filter 90 ngày vẫn có mức đạt 90 ngày và xu hướng hai cửa sổ 28 ngày kết thúc tại to. |
| AC23 | RULE lỗi hiện như dấu hiệu; cùng response/tag không đếm hai lần khi republish; đã ôn không xóa lịch sử; lỗi nháp không lộ. |
| AC24 | Kỳ không đủ chung bộ bài bị từ chối kích hoạt; kích hoạt sau opens_at hoặc đã có bài nộp bị chặn; không tự loại học sinh thiếu bài. |
| AC25 | Hai bài max 10,100 với điểm 8,60 cho điểm hạng 70.00; khác điểm kỹ năng gộp 68/110. Bốn điểm 90,80,80,70 cho hạng 1,2,2,4. |
| AC26 | Thiếu một bài thì INCOMPLETE, không 0/hạng; chờ chấm/công bố chặn FINAL; không nộp hết hạn được chốt INCOMPLETE. |
| AC27 | FINAL giữ snapshot khi chuyển lớp; republish điểm làm STALE, ẩn học sinh; recompute tạo revision mới và nguồn release đúng. |
| AC28 | Hủy bài/miễn người trong cohort làm INVALID; kỳ thay thế cần bộ bài mới chưa mở. FINAL/STALE không gia hạn/retake nếu chưa invalidate rõ ràng. |
| AC29 | STUDENT không xem bảng đầy đủ cấp trường/khối; peer lớp tiếng Anh chỉ alias, không student_id/tên/profile; CSV export chống công thức. |
| AC30 | Mobile 360/390 và desktop 1280, zoom 200%, bàn phím, focus dialog, reduced motion, lỗi form/empty/loading hoạt động; screenshot có dữ liệu giả thật. |
| AC31 | Chrome Android và Safari iOS ghi/nghe/upload được hoặc có fallback file rõ ràng; máy thật cần ghi phiên bản browser, không giả lập thay hoàn toàn. |
| AC32 | 1.000 hồ sơ, 100 phiên đồng thời trong 10 phút, autosave trung bình 10 giây/phiên và burst 100 submit; API save/submit p95 <1 giây, lỗi ngoài dự kiến <1%, không mất/nhân đôi câu. Media upload/report export đo riêng. Ghi cấu hình máy, dữ liệu và số đo thực tế. |
| AC33 | Asset chưa READY/khác user không đọc được; MIME giả/video/HTML bị từ chối; storage outage không trả upload/nộp thành công sai; attach-vs-cleanup không để response trỏ vào object vừa bị xóa. |
| AC34 | Restore DB+audio staging, đối chiếu dữ liệu và chạy smoke login/làm/chấm/xem; báo RPO/RTO đo được và áp lại tombstone trước mở traffic. |
| AC35 | Xóa một học sinh giả dọn cả nội dung trong JSON snapshot/audio, ranking INVALID, không xóa audio đề dùng chung; retry job an toàn; production không demo account/secret DEBUG. |

Dùng unit test cho công thức/parser, integration PostgreSQL cho quyền/giao dịch/race và browser test cho hành trình. Tối thiểu một test concurrent thật cho submit, save-vs-submit, retake-vs-publish và grade-release-vs-ranking-finalize; transaction rollback không để trạng thái nửa chừng. Không chỉ test happy path.

## 7. Điều kiện bàn giao

Code chạy từ DB rỗng theo README; tất cả migrations/test/ca quan trọng đạt, báo cáo tải và restore có số đo. Có OpenAPI hoặc bảng route đúng code, runbook tạo OWNER/MFA, cấp mã, backup/restore, rotation và xử lý sự cố. Ghi rõ ca nào cần môi trường/thiết bị thật chưa chạy; nếu AC31/32/34 chưa đạt thì chưa tuyên bố sẵn sàng production. Chủ dự án duyệt màn hình với một nhóm học sinh thử, cung cấp cấu hình cloud và chính sách dữ liệu trước mở truy cập thật.
