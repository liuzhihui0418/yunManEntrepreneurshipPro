import http.client
import mimetypes
from codecs import encode

conn = http.client.HTTPSConnection("yunwu.ai")
boundary = ''
payload = ''
headers = {
   'Accept': 'application/json',
   'Authorization': 'Bearer sk-Pr7mUz4qIAfcLgS2onczOTIceK57zGM8SsUIrabhIbJQZIef',
   'Content-type': 'multipart/form-data; boundary={}'.format(boundary)
}
conn.request("GET", "/v1/video/query?id=jimeng:jimeng:9f11cc3e-082b-4eaa-bd85-b3482a8005c7", payload, headers)
res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))