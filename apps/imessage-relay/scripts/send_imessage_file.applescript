on run argv
  set targetRecipient to item 1 of argv
  set targetFile to item 2 of argv

  tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy targetRecipient of targetService
    send (POSIX file targetFile as alias) to targetBuddy
  end tell
end run
