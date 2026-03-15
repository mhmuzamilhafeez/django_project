from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from proxy import handler


@csrf_exempt
def proxy_health(request):
    """Laravel: Route::get('/health')"""
    return handler.health()


@csrf_exempt
def proxy_test_connection(request):
    """Laravel: Route::get('/test-connection')"""
    return handler.test_connection()


@csrf_exempt
def proxy_forward(request, path=''):
    """Laravel: Route::any('/{any?}') - Main proxy route"""

    # CORS preflight - Laravel OPTIONS route ka equivalent
    if request.method == 'OPTIONS':
        response = HttpResponse('', status=200)
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
        response['Access-Control-Allow-Credentials'] = 'true'
        response['Access-Control-Max-Age'] = '86400'
        return response

    return handler.forward(request)
