$ErrorActionPreference = "Stop"
$src = "C:\Users\a\.dsh\remote-workspaces\wmv4mdfl29ql5\2_项目年度重要进展及成果的详细介绍.docx"
$pdf = "C:\Users\a\.dsh\remote-workspaces\wmv4mdfl29ql5\preview.pdf"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Open($src, $false, $true)
$pages = $doc.ComputeStatistics(2)
$doc.ExportAsFixedFormat($pdf, 17)
$doc.Close(0)
$word.Quit()
Write-Output ("PAGES=" + $pages)
