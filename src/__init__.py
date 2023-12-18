import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

email_format = textwrap.dedent(
    """
    <!DOCTYPE html>
    <html>
        <body>
        <table id="email_body" border="1">
            <tr style="background-color: #DCDCDC">
            <th>Timestamp</th>
            <th>Source</th>
            <th>Application</th>
            <th>Hostname</th>
            <th>Username</th>
            <th>Status</th>
            <th>Message</th>
            </tr>
            <tr>
            <td>%(asctime)s</td>
            <td>%(pathname)s</td>
            <td>%(application)s</td>
            <td>%(node)s</td>
            <td>%(status)s</td>
            <td>$(message)s</td>
            </tr>
        </table>
        </body>
    </html>
"""
)
