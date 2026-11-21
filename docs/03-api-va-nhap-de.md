# API và nhập dữ liệu

## Hợp đồng chung

Prefix `/api/v1`, cùng origin, session cookie Django, CSRF cho mọi method không an toàn, gồm POST/PUT/PATCH/DELETE kể cả login/logout. JSON UTF-8, UUID dạng string, timestamp RFC3339 có offset, điểm là chuỗi decimal. API không nhận `student_id`, role, points hoặc is_correct từ học sinh để quyết định quyền/chấm. Server suy user từ session. Không tự fetch URL do người dùng nhập.

Thành công trả `{data:...}`; danh sách thêm `{page,page_size,total}`, page_size mặc định 25, tối đa 100, sort whitelist. Lỗi trả `{error:{code,message,fields?,request_id}}`; không stack trace. 400 JSON sai; 401 chưa đăng nhập; 403 hành động không được phép/CSRF; 404 tài nguyên không thuộc quyền để tránh dò; 409 revision hoặc trạng thái xung đột; 413 quá dung lượng; 422 dữ liệu không hợp lệ; 429 rate limit; 503 hạ tầng tạm lỗi. `fields` là map field -> danh sách thông báo, không chứa dữ liệu người khác.

Optimistic lock bắt buộc cho ExamVersion, Assignment, Attempt/Response/Grade và RankingPeriod: request sửa có `expected_revision` hoặc tên revision chuyên biệt trong bảng API; thiếu trả 422, lệch trả 409 với current_revision. User/School/Class/Tag chưa dùng/ErrorReview và thông tin đơn giản dùng transaction, last-write-wins có chủ đích. Membership/recipient/code dùng khóa và kiểm tra trạng thái server, không yêu cầu revision chưa tồn tại; thao tác của chúng ảnh hưởng aggregate thì tăng revision aggregate tương ứng. Tạo tài nguyên nếu không ghi khác trả 201; cập nhật 200; xóa nháp 204. Log chỉ request_id, route template, status, duration và actor_id khi cần; không body, cookie, mã, URL fragment, tên tệp nhạy cảm.

## API học sinh và xác thực

| Method và path | Đầu vào | Kết quả/quy tắc |
|---|---|---|
| GET /auth/csrf | Không | CSRF cookie/token, no-store. |
| POST /auth/student-login | code, remember_device boolean | user{id,display_name,role}, session_expires_at; đổi session key. Mã không hợp lệ trả 401 INVALID_CODE chung. |
| POST /auth/logout | Không | Hủy session, 204. |
| GET /me | Không | Hồ sơ tối thiểu, remember_device, server_time; không trả mã cá nhân. |
| GET /classes/resolve?code=... | Mã lớp công khai | Trang lớp của chính học sinh; không danh sách bạn. |
| GET /assignments/resolve?code=... | Mã bài công khai | Assignment được nhận; sai quyền 404. |
| GET /assignments | status?, page | Bài của mình, effective status, due_at, late_until, current_attempt_id. |
| GET /assignments/{id} | Không | Metadata và đề sau opens_at, quyền câu hỏi lọc bí mật; trước opens_at chỉ metadata. |
| POST /assignments/{id}/start | Không | attempt_id, revision, responses; gọi lại trả current attempt 200. |
| GET /attempts/{id} | Không | Bài của mình, revision, responses và save state; không grade nội bộ. |
| PUT /attempts/{id}/responses/{question_id} | expected_revision, text_answer hoặc option_ids hoặc audio_asset_id | Trả response_revision và attempt_revision. Trường đúng loại câu, option đúng câu; chỉ gắn asset READY thuộc response này; null audio để gỡ cả READY/pending/rejected rõ ràng. |
| POST /attempts/{id}/audio/init | question_id, expected_response_revision | 201 asset_id UPLOADING, response_revision, attempt_revision; gắn pending asset vào response để server chặn submit trong lúc tải. |
| POST /assets/{id}/upload | multipart: file | Chỉ asset UPLOADING gắn response của mình đang làm; kiểm tra bytes rồi trả READY và revisions. Lỗi giữ trạng thái REJECTED để retry bằng init mới hoặc gỡ rõ ràng. |
| POST /attempts/{id}/submit | expected_attempt_revision; header Idempotency-Key UUID | status,submitted_at,attempt_id. Không trả điểm. |
| GET /attempts/{id}/result | Không | Latest release và lịch sử được phép; chưa release trả published:false, status, không grade. |
| GET /assignments/{id}/answers | Không | Chỉ sau answers release; đáp án/giải thích/transcript. Trước đó 403 ANSWERS_NOT_RELEASED. |
| GET /progress | from?,to? ngày YYYY-MM-DD | Bốn kỹ năng, sample_count, labels/trend, tiến độ; khoảng tối đa 366 ngày, mặc định 28 ngày. Mức đạt theo khoảng chọn; xu hướng luôn hai cửa sổ 28 ngày kết thúc tại to, trả trend_current_from/to và trend_previous_from/to rõ ràng. |
| GET /errors | skill?,tag?,reviewed?,page | Occurrences đã công bố của mình, nhóm/chi tiết, không lỗi chấm nháp. |
| PATCH /errors/{id}/review | reviewed boolean | Chỉ đặt/xóa student_reviewed_at của mình. |
| GET /rankings | Không | Các kỳ FINAL mình thuộc, số đủ bài/tổng cohort, hạng của mình. |
| GET /rankings/{id} | Không | Kết quả bản thân; peers chỉ khi scope/class và show_peers hợp lệ. Không trả student_id trong peer entries. |
| GET /assets/{id}/content | assignment_id hoặc response_id | Proxy audio với Range, kiểm tra quyền ngữ cảnh mỗi request, không redirect URL công khai; trả bytes không JSON. |

Response đã nộp đọc được bởi chính học sinh nhưng không sửa được. Kết quả attempt cũ đã có release được xem trong lịch sử, không nhận là kết quả chính thức hiện tại. Xác thực OWNER sử dụng routes của django-two-factor-auth; không mở đường login API bỏ qua TOTP.

Ví dụ autosave:

```json
{"expected_revision":3,"option_ids":["22222222-2222-4222-8222-222222222222"]}
```

```json
{"data":{"response_revision":4,"attempt_revision":12,"saved_at":"2026-11-11T08:00:00Z"}}
```

Nộp sử dụng revision mới nhất từ toàn bộ request đã hoàn tất. Một response request thành công tăng attempt revision; client lấy max revision khi nhiều response được lưu đồng thời, không dùng thứ tự response HTTP đến. 409 submit trả current revision và yêu cầu tải/đối chiếu nháp; không tự submit lại với revision mới.

Idempotency: tạo key một lần cho thao tác nộp và giữ qua retry. Cùng key/digest trả cùng status/body thành công, kể cả sau hạn. Key khác sau khi đã nộp trả receipt hiện có nếu yêu cầu là nộp cùng attempt, không chấm lại; key bị dùng với payload khác trả 409 IDEMPOTENCY_CONFLICT. Lỗi validation không tạo receipt thành công. Receipt lưu cùng vòng đời attempt.

## API OWNER

Mọi route dưới prefix `/owner`. TOTP verified session bắt buộc. CRUD lấy fields đúng schema 02 và whitelist theo bảng dưới, không generic mass assignment. GET detail/list tương ứng với mỗi tài nguyên, có pagination. DELETE chỉ DRAFT chưa tham chiếu, đối tượng nghiệp vụ đã dùng dùng archive/cancel.

| Nhóm | Route/action và dữ liệu |
|---|---|
| Học sinh | POST /students {student_ref,display_name}; PATCH /students/{id} {display_name,status}; POST /students/{id}/rotate-code {} cần MFA mới, trả mã thô một lần; POST /students/{id}/revoke-sessions {}; GET /students/{id}/progress?from&to. |
| Trường/lớp | CRUD /schools {code,name}, /school-classes {school_id,school_year,grade,name}, /english-classes {name,school_year}; code lớp server sinh. PATCH archive riêng. |
| Thành viên | POST /students/{id}/school-transfer {school_class_id,effective_at}; POST /english-classes/{id}/members {student_id,start_at}; POST /english-classes/{id}/members/{student_id}/leave {end_at}. Chỉ cho timestamp không ở tương lai ở V1; cấm chỉnh chồng khoảng. |
| Đề | POST /exams {title}; POST /exams/{id}/versions {}; PATCH /versions/{id} {expected_revision}; POST /versions/{id}/clone {}; POST /versions/{id}/publish {expected_revision}; POST archive. PATCH /exams/{id} {title} sửa tên; không thay nhãn snapshot của bài đã giao. |
| Câu/tài liệu | CRUD /versions/{id}/questions, /passages; sửa luôn khóa version và tăng version revision. Payload question theo định dạng import bên dưới, có rubric đầy đủ; server sinh IDs. Tải audio qua POST /assets {file,purpose:PROMPT_AUDIO}; chỉ gắn READY của OWNER. |
| Tag | CRUD /tags {kind,skill,name}; đã dùng chỉ archive, không rename. |
| Nhập | POST /imports/preview {file,kind}; GET /imports/{id}; POST /imports/{id}/commit {expected_digest,target_exam_id? hoặc class_id?}; commit all-or-nothing. |
| Giao bài | POST /assignments {version_id,title,class_ids,opens_at,due_at,late_policy,late_until}; POST /assignments/{id}/publish {expected_revision}; POST /extend {expected_revision,due_at,late_until,reason}; POST /cancel {reason,expected_revision}. |
| Người nhận | POST /assignments/{id}/recipients {student_ids,reason}; POST /recipients/{id}/exempt {reason}; POST /recipients/{id}/retake {reason}; các thao tác có thể ảnh hưởng ranking phải trả cảnh báo trước ở UI. |
| Chấm | GET /grading-queue; GET /attempts/{id}/grading; PUT /responses/{id}/grade {expected_revision,criterion_levels,feedback,criterion_notes,reason}; POST/PATCH /responses/{id}/errors {tag_id,note,anchor,expected_revision}; POST /attempts/{id}/publish-result {expected_revision,reason?}. Không nhận total_points. |
| Đáp án | POST /assignments/{id}/release-answers {expected_revision}; check thời điểm và người nhận chưa miễn. |
| Báo cáo | GET /reports/progress?from&to&school_id&grade&school_class_id&english_class_id; GET /reports/export.csv cùng filter, tối đa 1.000 học sinh, cần MFA mới; grade không có school_id trả 422. |
| Ranking | CRUD /ranking-periods {name,school_year,start_at,end_at,scope,scope_target,student_ids,assignment_ids,show_peers}; POST /{id}/activate, /finalize, /recompute-publish, /invalidate {expected_revision,reason?}. |
| Dữ liệu | POST /privacy-requests {student_id,kind,reason}; GET /privacy-requests/{id}; xử lý xóa/export qua workflow tài liệu 05, không GET gây xóa. |

Đối tượng chưa có revision riêng dùng revision aggregate: lỗi và chấm dùng attempt revision; grade endpoint nhận thêm grade_revision khi sửa grade đã có, grade_revision=0 nghĩa là tạo mới. Thay grade/error tăng attempt revision; publish đòi current attempt đúng recipient. Chuyển lớp/suspend/archive dùng transaction và không cho generic patch trường lịch sử. Agent xuất OpenAPI hoặc bảng route tự sinh từ ứng dụng, kiểm thử endpoint theo đặc tả này.

## Nhập đề CSV/XLSX

V1 nhận một đề mỗi file. CSV UTF-8 có header, chấp nhận BOM; XLSX một sheet tên `questions`. Không nhận .xls, .xlsm, file có macro, công thức, external link, HTML, ZIP tài nguyên hoặc URL media. File <=2 MiB, <=100 câu, tối đa 500 KiB tổng text sau parse; XLSX tổng uncompressed <=10 MiB, <=100 entry ZIP. Parser không tải external resource, dùng defusedxml. Báo số dòng lỗi; preview không ghi Question, commit là transaction. Nếu bất kỳ dòng lỗi thì không cho commit. File gốc xóa sau parse, payload preview hết hạn 24 giờ.

| Cột | Quy tắc |
|---|---|
| position | Số 1..N liên tục, không trùng. |
| type | SINGLE_CHOICE/MULTIPLE_CHOICE/TEXT/AUDIO. |
| skill | READING/LISTENING/WRITING/SPEAKING theo ma trận. |
| difficulty | FOUNDATION/STANDARD/CHALLENGE, bắt buộc. |
| prompt | Thuần text 1..10.000 ký tự. |
| max_points | Decimal dùng dấu chấm, 0.01..100.00. |
| option_a..option_f | 2..6 nội dung liên tục từ A, mỗi lựa chọn <=2.000 ký tự; TEXT/AUDIO phải trống. |
| correct_options | A cho SINGLE, A\|C cho MULTIPLE, không trùng, chỉ các lựa chọn có nội dung; TEXT/AUDIO phải trống. |
| passage_ref | Trống hoặc mã tài liệu nội bộ trong file. |
| passage_text | Nội dung <=20.000 ký tự, lặp ref phải trùng chính xác. |
| audio_asset_id | UUID của PROMPT_AUDIO READY do OWNER tải trước, lặp ref phải cùng asset. LISTENING bắt buộc passage_ref+audio_asset_id. |
| transcript | Thuần text tùy chọn, lặp ref phải trùng; không hiển thị trước answers release. |
| topic_tags | Một hoặc nhiều tên tag cùng kỹ năng, phân cách \|, tối thiểu 1. |
| error_tags | Tên tag lỗi tùy chọn phân cách \|. |
| explanation | Giải thích chuẩn tùy chọn, chỉ sau answers release. |

TEXT/AUDIO được tạo rubric mặc định BR-06 khi nhập, giáo viên chỉnh trên màn hình preview sau commit DRAFT trước publish. Tag chưa có được tạo khi commit, preview liệt kê tag mới. Passage không có ref thì các trường passage_text/audio_asset_id/transcript phải rỗng. File không có tiêu đề đề: nhập title ở form preview. Mẫu `examples/questions.csv` nhập được ngay, không có audio giả.

Import tạo DRAFT mới, không tự publish/giao bài. Retry commit cùng batch trả đúng version đã tạo, không nhân đôi câu/tag. Import vào Exam có sẵn tạo number kế tiếp dưới khóa Exam. Tệp chứa công thức trong XLSX bị từ chối; CSV được đọc như text, không thực thi. Khi export CSV, chống formula injection với ô bắt đầu =,+,-,@,tab,CR; quote CSV đúng chuẩn và thêm dấu nháy đơn cho nội dung nguy hiểm.

## Nhập học sinh

CSV/XLSX sheet `students`, <=2 MiB, <=1.000 dòng. Cột bắt buộc student_ref,display_name. Tùy chọn school_code,school_year,grade,school_class_name; hoặc đủ cả bốn hoặc đều rỗng. Trường/lớp phải tồn tại, preview báo thiếu để tạo trước. class_id lớp tiếng Anh được chọn ở form, không trong file. student_ref trùng trong file lỗi; trùng DB được preview là “đã tồn tại”, không sửa tên hay chuyển lớp âm thầm; chỉ thêm membership lớp tiếng Anh nếu chưa có. Thay đổi hồ sơ thực hiện qua thao tác riêng. Không đưa mã bí mật vào tệp nhập/xuất báo cáo.
