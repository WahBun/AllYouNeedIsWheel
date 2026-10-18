-- Use Xcode's documented Build command. Never Run, Test, Debug, or install.
on run arguments
    if (count arguments) is not 3 then error "Expected project path, device identifier, and build log path."
    set projectPath to item 1 of arguments
    set expectedDevice to item 2 of arguments
    set logPath to item 3 of arguments
    set targetWorkspace to missing value
    with timeout of 1300 seconds
        tell application "Xcode"
            open (POSIX file projectPath)
            repeat 120 times
                repeat with candidate in workspace documents
                    try
                        set candidateFile to get file of candidate
                        set candidatePath to POSIX path of candidateFile
                        if candidatePath is projectPath or candidatePath is (projectPath & "/") then
                            if loaded of candidate then set targetWorkspace to candidate
                        end if
                    end try
                end repeat
                if targetWorkspace is not missing value then exit repeat
                delay 0.5
            end repeat
            if targetWorkspace is missing value then error "The isolated renewal project did not finish loading."
            set active scheme of targetWorkspace to scheme "Wheel" of targetWorkspace
            set targetDestination to missing value
            repeat with candidate in run destinations of targetWorkspace
                if platform of candidate is "iphoneos" then
                    if device identifier of device of candidate is expectedDevice then
                        set targetDestination to candidate
                        exit repeat
                    end if
                end if
            end repeat
            if targetDestination is missing value then error "The configured iPhone is unavailable to Xcode. Connect it and try again."
            set active run destination of targetWorkspace to targetDestination
            set actionResult to build targetWorkspace
            repeat 2400 times
                if completed of actionResult then exit repeat
                delay 0.5
            end repeat
            if not (completed of actionResult) then error "Xcode Build timed out. Inspect Xcode before retrying."
            set resultLog to build log of actionResult
            set resultStatus to status of actionResult
        end tell
        set logFile to open for access (POSIX file logPath) with write permission
        try
            set eof logFile to 0
            write resultLog to logFile as «class utf8»
            close access logFile
        on error messageText number errorNumber
            try
                close access logFile
            end try
            error messageText number errorNumber
        end try
        tell application "Xcode"
            if resultStatus is not succeeded then error "Xcode Build failed. See the saved build log."
        end tell
        return "Xcode Build completed. No iPhone installation was performed."
    end timeout
end run
