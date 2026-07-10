on run argv
  set targetRecipient to item 1 of argv
  set targetMessage to item 2 of argv

  tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy targetRecipient of targetService
    send targetMessage to targetBuddy
  end tell
end run
