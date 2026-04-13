# Codebase Concerns

**Analysis Date:** 2026-04-13

## Tech Debt

**Temp Files Not Cleaned Up:**
- Issue: Temporary image files are created but never deleted
- Files: `src/desktop_pet/pet.py` (lines 218-219, 239-240, 254-255, 268-269)
- Impact: Disk space pollution in pet package directories (temp_fixed.png, temp_flying_fixed.png)
- Fix approach: Add cleanup on pet switch or application exit, or use in-memory processing

**Bare Exception Handlers:**
- Issue: Multiple bare `except:` clauses that catch all exceptions including KeyboardInterrupt
- Files: `src/desktop_pet/config_manager.py` (line 300), `src/desktop_pet/setup_wizard.py` (line 353)
- Impact: Hides real errors, makes debugging difficult
- Fix approach: Use specific exception types

**State Machine Complexity:**
- Issue: DesktopPet class handles multiple states (IDLE, DRAGGING, FALLING, INERTIA, REST_REMINDER, MOTION_MODE, ANIMATING) with complex transitions
- Files: `src/desktop_pet/pet.py` (entire 1186-line file)
- Impact: Hard to maintain, potential for state inconsistencies
- Fix approach: Extract state management to separate class

**Duplicated Image Loading Logic:**
- Issue: Image loading code duplicated in multiple places (initUI, _switch_to_pet)
- Files: `src/desktop_pet/pet.py` (lines 203-277, 726-765)
- Impact: Code duplication, inconsistent behavior
- Fix approach: Extract to helper method

## Known Bugs

**API Server IP Filter Disabled:**
- Symptom: IP whitelist can be bypassed using ngrok or similar tools
- Files: `src/desktop_pet/api_server.py` (line 111)
- Trigger: When `_allowed_ips` is empty (comment: "IP 白名单已禁用")
- Workaround: Not applicable - designed behavior for tunneling

**CORS Allows All Origins:**
- Symptom: API server accepts requests from any origin
- Files: `src/desktop_pet/api_server.py` (line 153)
- Impact: Potential for cross-site requests
- Workaround: Configure specific allowed origins if security needed

**Motion Controller Direct State Access:**
- Symptom: MotionModeController sets pet state directly via `self._pet.state = self._pet.state.MOTION_MODE`
- Files: `src/desktop_pet/motion_controller.py` (line 151)
- Trigger: When resuming motion after rest reminder
- Impact: Violates encapsulation, could cause race conditions
- Workaround: Use signals/slots for state changes

## Security Considerations

**API Has No Authentication:**
- Risk: Anyone on the network can control the pet position and animations
- Files: `src/desktop_pet/api_server.py`
- Current mitigation: IP whitelist (can be disabled)
- Recommendations: Add API key or token authentication

**CORS Wildcard:**
- Risk: Any website can make requests to the API
- Files: `src/desktop_pet/api_server.py` (line 153)
- Current mitigation: None
- Recommendations: Restrict to specific origins or implement CORS properly

**Callback URL Validation Incomplete:**
- Risk: SSRF via animation callback URLs
- Files: `src/desktop_pet/api_server.py` (lines 183-212)
- Current mitigation: Basic IP range blocking
- Recommendations: Add DNS rebinding protection, timeout on callbacks

**Config File Injection:**
- Risk: User config could contain malicious Python code via config
- Files: `src/desktop_pet/config_manager.py`
- Current mitigation: None
- Recommendations: Add config schema validation

## Performance Bottlenecks

**Image Processing on Startup:**
- Problem: Every pet switch reloads and processes images with PIL
- Files: `src/desktop_pet/pet.py` (lines 216-220, 236-240)
- Cause: Image.open() called on every pet switch
- Improvement path: Cache processed images, use QPixmap directly

**Animation Loading:**
- Problem: Animations loaded on-demand but not cached per-session
- Files: `src/desktop_pet/pet.py` (_load_pet_animation)
- Cause: QMovie created every time animation plays
- Improvement path: Use action_manager movie caching consistently

**Timer Overhead:**
- Problem: Multiple QTimers running simultaneously (movement_timer, rest_timer, countdown_timer, rest_timer_display, animation_timer, inertia_timer, gravity_timer)
- Files: `src/desktop_pet/pet.py`
- Impact: CPU usage even when idle
- Improvement path: Consolidate timers, use single event loop

## Fragile Areas

**Pet Package Loading:**
- Why fragile: No graceful handling of missing animation files
- Files: `src/desktop_pet/pet_loader.py`, `src/desktop_pet/pet.py` (_load_pet_animations)
- Safe modification: Validate package structure before loading
- Test coverage: None

**API Server Threading:**
- Why fragile: Runs in daemon thread with separate event loop
- Files: `src/desktop_pet/api_server.py` (lines 876-880)
- Safe modification: Ensure thread-safe access to pet state
- Test coverage: None

**Context Menu Creation:**
- Why fragile: Rebuilds menu on every right-click, could fail if pet package is None
- Files: `src/desktop_pet/pet.py` (lines 656-716)
- Safe modification: Add null checks for current_pet_package
- Test coverage: None

**Coordinate Validation:**
- Why fragile: Limited bounds checking, allows negative coordinates
- Files: `src/desktop_pet/api_server.py` (lines 160-172)
- Safe modification: Validate against actual screen dimensions
- Test coverage: None

## Scaling Limits

**Single Pet Instance:**
- Current capacity: Only one pet instance per application
- Limit: Cannot run multiple pets simultaneously
- Scaling path: Not designed for multiple instances

**Animation Frame Rate:**
- Current capacity: Hardcoded to animation file FPS
- Limit: Cannot dynamically adjust playback speed
- Scaling path: Add speed control parameter

**API Request Rate:**
- Current capacity: No rate limiting
- Limit: Could be overwhelmed by rapid requests
- Scaling path: Add request throttling

## Dependencies at Risk

**PyQt6:**
- Risk: Large dependency, platform-specific binaries
- Impact: Installation issues on some platforms
- Migration plan: Consider QtPy abstraction for future

**aiohttp:**
- Risk: Async HTTP server adds complexity
- Impact: Threading complexity in desktop app
- Migration plan: Could use Quart or FastAPI with WSGI adapter

**Pillow:**
- Risk: Image processing heavy
- Impact: Startup time, memory usage
- Migration plan: Use Qt's image classes where possible

## Missing Critical Features

**No Unit Tests:**
- Problem: Zero test coverage in src/ directory
- Blocks: Safe refactoring, regression detection
- Priority: High

**No Error Recovery:**
- Problem: Application crashes on corrupted animation files
- Blocks: Reliability in production
- Priority: High

**No Logging for API:**
- Problem: API requests only logged at DEBUG level
- Blocks: Production debugging
- Priority: Medium

**No Configuration UI:**
- Problem: All config via JSON files
- Blocks: User-friendly configuration
- Priority: Medium

## Test Coverage Gaps

**Core Pet Logic:**
- What's not tested: State transitions, animation playback, movement
- Files: `src/desktop_pet/pet.py`
- Risk: State machine bugs could go unnoticed
- Priority: High

**Config Manager:**
- What's not tested: Config loading, merging, validation
- Files: `src/desktop_pet/config_manager.py`
- Risk: Config errors could crash application
- Priority: High

**API Server:**
- What's not tested: All endpoints, validation, error handling
- Files: `src/desktop_pet/api_server.py`
- Risk: API bugs not caught before deployment
- Priority: High

**Pet Loader:**
- What's not tested: Package validation, loading
- Files: `src/desktop_pet/pet_loader.py`
- Risk: Invalid packages could cause issues
- Priority: Medium

---

*Concerns audit: 2026-04-13*