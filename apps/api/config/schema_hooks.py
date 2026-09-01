def require_entry_create_body(result, generator, request, public):
    """Restore body-required metadata lost by the top-level polymorphic schema.

    drf-spectacular infers request-body presence from top-level required fields.
    A oneOf component has those fields only inside its variants, so the body is
    otherwise emitted as optional even though both variants require it.
    """
    del generator, request, public
    result["paths"]["/api/entries/"]["post"]["requestBody"]["required"] = True
    return result
