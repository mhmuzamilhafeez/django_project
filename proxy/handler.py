import gzip
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAIN_DOMAIN = getattr(settings, 'PROXY_MAIN_DOMAIN', '').rstrip('/')
PROXY_PREFIX = getattr(settings, 'PROXY_PREFIX', 'proxy')
TIMEOUT = getattr(settings, 'PROXY_TIMEOUT', 120)
VERIFY_SSL = getattr(settings, 'PROXY_VERIFY_SSL', False)
DEBUG_MODE = getattr(settings, 'PROXY_DEBUG', False)


def build_target_url(request):
    """Laravel: buildTargetUrl()"""
    path = request.path.lstrip('/')
    # proxy/ prefix hata do
    prefix = PROXY_PREFIX.strip('/') + '/'
    if path.startswith(prefix):
        path = path[len(prefix):]

    url = MAIN_DOMAIN + '/' + path.lstrip('/')

    query = request.META.get('QUERY_STRING', '')
    if query:
        url += '?' + query

    return url


def extract_headers(request):
    """Laravel: extractHeaders() - Brotli fix included"""
    headers = {
        # FIX: br/brotli hatao, sirf gzip deflate
        'Accept-Encoding': 'gzip, deflate',
        'Accept': 'application/json',
        'Content-Type': request.content_type or 'application/json',
        'User-Agent': request.META.get('HTTP_USER_AGENT', 'Django-Proxy/1.0'),
        'X-Forwarded-For': request.META.get('REMOTE_ADDR', ''),
        'X-Real-IP': request.META.get('REMOTE_ADDR', ''),
    }

    # Authorization token
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if auth:
        headers['Authorization'] = auth

    # Extra headers
    for header in ['HTTP_X_REQUESTED_WITH', 'HTTP_ACCEPT_LANGUAGE', 'HTTP_CACHE_CONTROL']:
        value = request.META.get(header, '')
        if value:
            key = header.replace('HTTP_', '').replace('_', '-').title()
            headers[key] = value

    return {k: v for k, v in headers.items() if v}


def is_gzipped(data: bytes) -> bool:
    """Laravel: isGzipped()"""
    return len(data) >= 2 and data[0] == 0x1f and data[1] == 0x8b


def rewrite_urls(body: str, proxy_domain: str) -> str:
    """Laravel: rewriteUrls()"""
    proxy_base = proxy_domain + '/' + PROXY_PREFIX
    body = body.replace(MAIN_DOMAIN, proxy_base)
    return body


def forward(request):
    """Laravel: forward() - Main proxy function"""
    from django.http import HttpResponse, JsonResponse

    proxy_domain = request.scheme + '://' + request.get_host()
    target_url = build_target_url(request)
    method = request.method.upper()

    if DEBUG_MODE:
        logger.info(f'Proxy Request | {method} | {target_url}')

    try:
        headers = extract_headers(request)
        session = requests.Session()

        # FIX: curl options ka Django equivalent
        kwargs = {
            'headers': headers,
            'timeout': TIMEOUT,
            'verify': VERIFY_SSL,
            'allow_redirects': False,
            'stream': True,  # decode_content=False ka equivalent
        }

        # Files hain to multipart
        if request.FILES:
            files = {}
            for key, file in request.FILES.items():
                files[key] = (file.name, file.read(), file.content_type)
            data = {k: v for k, v in request.POST.items()}
            kwargs['files'] = files
            kwargs['data'] = data
        elif method == 'GET':
            pass
        elif 'application/json' in (request.content_type or ''):
            kwargs['data'] = request.body
        else:
            kwargs['data'] = request.POST.dict()

        response = session.request(method, target_url, **kwargs)

        if DEBUG_MODE:
            logger.info(f'Proxy Response | {response.status_code}')

        # Body lo
        body = response.content

        # Gzip decompress
        if is_gzipped(body):
            try:
                body = gzip.decompress(body)
            except Exception:
                pass

        body = body.decode('utf-8', errors='replace')

        # URL rewrite
        body = rewrite_urls(body, proxy_domain)

        # Response banao
        content_type = response.headers.get('Content-Type', 'application/json')
        proxy_response = HttpResponse(body, status=response.status_code, content_type=content_type)

        # Extra headers
        for header in ['Cache-Control', 'ETag', 'Last-Modified', 'Expires']:
            if header in response.headers:
                proxy_response[header] = response.headers[header]

        # CORS headers
        proxy_response['Access-Control-Allow-Origin'] = '*'
        proxy_response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        proxy_response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept'
        proxy_response['Access-Control-Allow-Credentials'] = 'true'

        return proxy_response

    except Exception as e:
        logger.error(f'Proxy Error: {str(e)}')
        message = str(e) if DEBUG_MODE else 'Connection failed. Please try again.'
        return JsonResponse({
            'status': 'error',
            'message': message,
            'error_code': 'PROXY_ERROR',
        }, status=502, headers={'Access-Control-Allow-Origin': '*'})


def health():
    """Laravel: health()"""
    from django.http import JsonResponse
    return JsonResponse({
        'status': 'success',
        'message': 'Proxy is active',
        'main_domain': MAIN_DOMAIN,
    }, headers={'Access-Control-Allow-Origin': '*'})


def test_connection():
    """Laravel: testConnection() - FIXED"""
    from django.http import JsonResponse
    try:
        response = requests.get(
            MAIN_DOMAIN + '/apps?days=1',
            headers={
                'Accept-Encoding': 'gzip, deflate',  # FIX: no brotli
                'Accept': 'application/json',
                'User-Agent': 'Django-Proxy/1.0',
            },
            timeout=30,
            verify=False,
            stream=True,
        )

        body = response.content
        if is_gzipped(body):
            try:
                body = gzip.decompress(body)
            except Exception:
                pass

        body_str = body.decode('utf-8', errors='replace')

        return JsonResponse({
            'status': 'success',
            'message': 'Main domain is reachable',
            'response_status': response.status_code,
            'response_preview': body_str[:200],
        }, headers={'Access-Control-Allow-Origin': '*'})

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'Cannot reach main domain',
            'error': str(e),
        }, status=502, headers={'Access-Control-Allow-Origin': '*'})
