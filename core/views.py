from django.shortcuts import render


def launcher(request):

    return render(
        request,
        "core/launcher.html"
    )