' 静默启动（无 console 窗口）
' 优先 pyw launcher，回退 pythonw（避免 Microsoft Store 沙盒版 python 静默失败）
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
script = """" & dir & "\main.py"""

On Error Resume Next
ret = sh.Run("pyw " & script, 0, False)
If Err.Number <> 0 Then
    Err.Clear
    sh.Run "pythonw " & script, 0, False
End If
On Error Goto 0
