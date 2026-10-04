(in-package :star-wpa)

(defparameter *python-executable* (or (uiop:getenv "STAR_WPA_PYTHON") "python3"))

(defun adapter-handler (capability root)
  (lambda (message state runtime)
    (declare (ignore runtime))
    ;; The local adapter message is a request filename, not an ad-hoc StarIntel dtype.
    ;; Portable contracts are enforced by the schema-locked adapter on emitted docs.
    (unless (and (stringp message) (probe-file message))
      (error "Wireless adapter expects an existing operator-local request file."))
    (let ((result (starprocessport:run-process
                   *python-executable*
                   (list "-m" "star_wpa" capability "--request" (namestring (truename message)))
                   :directory root :timeout 345 :stdout-limit (* 16 1024 1024)
                   :stderr-limit 4096)))
      (starprocessport:ensure-process-success result)
      (when (starprocessport:process-result-stdout-truncated-p result)
        (error "Wireless adapter output exceeded its bounded observation limit."))
      (values (starprocessport:process-result-stdout result) (1+ (or state 0))))))

(defun start-wireless-runtime ()
  "Compile actual .star declarations and register them with the maintained runtime."
  (let ((runtime (starlangruntime:make-runtime))
        (root (asdf:system-source-directory "star-wpa")))
    (let ((source (uiop:getenv "STARLANG_SOURCE")))
      (unless source (error "STARLANG_SOURCE must name the locked runtime."))
      (dolist (system '("starlang-compiler" "starlang-runtime" "star-process-port"))
        (unless (equal (truename (asdf:system-source-directory system))
                       (truename (merge-pathnames (format nil "~A/" system)
                                                 (uiop:ensure-directory-pathname source))))
          (error "Loaded StarLang system does not originate from the locked checkout."))))
    (uiop:run-program
     (list *python-executable* (namestring (merge-pathnames "scripts/check-runtime-pin.py" root)))
     :output :string :error-output :string)
    (uiop:run-program
     (list *python-executable* (namestring (merge-pathnames "scripts/build-tool-actors.py" root)) "--check")
     :output :string :error-output :string)
    (handler-case
        (progn
          (dolist (source
                    (append (mapcar (lambda (name) (merge-pathnames (format nil "actors/~A.star" name) root))
                                    '("kismet" "gpsd" "listener" "aircrack" "deauth" "trilateration" "wardrive"))
                            (sort (directory (merge-pathnames "actors/tools/*.star" root))
                                  #'string< :key #'namestring)))
            (let* ((capability (if (search "/tools/" (namestring source))
                                   (format nil "tool-~A" (pathname-name source))
                                   (pathname-name source)))
                   (ir (starlangcompiler:compile-actor-file source))
                   (expected-handler (format nil "wpa-~A-handler" capability)))
              (unless (string= expected-handler (getf ir :handler))
                (error "Unbound wireless handler in compiled declaration."))
              (starlangruntime:spawn
               runtime
               (starlangruntime:make-native-actor-definition
                (getf ir :name) (adapter-handler capability root)
                :service-uri (getf ir :service-uri)
                :accepts (getf ir :accepts) :produces (getf ir :produces)
                :restart-policy (getf ir :restart)
                :mailbox-capacity (getf (getf ir :mailbox) :capacity)
                :initial-state 0 :metadata (getf ir :metadata)))))
          runtime)
      (error (condition)
        (starlangruntime:shutdown-runtime runtime)
        (error condition)))))

(defun dispatch (runtime capability request-file)
  "ASK the native actor through its real bounded mailbox; returns canonical JSON."
  (starlangruntime:ask runtime (format nil "wpa-~A" capability) request-file))
