package httpapi

type HTTPError struct {
	Status int
	Msg    string
}

func (e *HTTPError) Error() string { return e.Msg }

func NewHTTPError(status int, msg string) *HTTPError {
	return &HTTPError{Status: status, Msg: msg}
}

var (
	ErrNotFound      = &HTTPError{Status: 404, Msg: "Not found"}
	ErrUnauthorized  = &HTTPError{Status: 401, Msg: "Unauthorized"}
	ErrForbidden     = &HTTPError{Status: 403, Msg: "Forbidden"}
	ErrBadRequest    = &HTTPError{Status: 400, Msg: "Bad request"}
	ErrConflict      = &HTTPError{Status: 409, Msg: "Conflict"}
	ErrPayloadTooBig = &HTTPError{Status: 413, Msg: "Payload too large"}
)
