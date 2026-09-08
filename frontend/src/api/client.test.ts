import { describe, it, expect, vi, beforeEach } from 'vitest';
   import { apiFetch, ApiError } from './client';

   describe('apiFetch', () => {
     beforeEach(() => {
       vi.restoreAllMocks();
     });

     it('returns parsed json on success', async () => {
       const mockData = { id: '1', name: 'Test Target' };
       const mockResponse = new Response(JSON.stringify(mockData), {
         status: 200,
         headers: { 'Content-Type': 'application/json' },
       });
       vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

       const result = await apiFetch('/targets');
       expect(result).toEqual(mockData);
       expect(fetch).toHaveBeenCalledWith('http://localhost:8000/targets', expect.any(Object));
     });

     it('throws ApiError with detail on non-2xx response', async () => {
       const mockErrorBody = { detail: 'SSRF guard: blocked domain' };
       const makeMockResponse = () => new Response(JSON.stringify(mockErrorBody), {
         status: 400,
         headers: { 'Content-Type': 'application/json' },
       });
       vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse());

       await expect(apiFetch('/targets')).rejects.toThrow(ApiError);
       
       vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse());
       try {
         await apiFetch('/targets');
       } catch (err: unknown) {
         expect(err).toBeInstanceOf(ApiError);
         const apiError = err as ApiError;
         expect(apiError.status).toBe(400);
         expect(apiError.detail).toBe('SSRF guard: blocked domain');
       }
     });

     it('handles empty 204 responses', async () => {
       const mockResponse = new Response(null, {
         status: 204,
       });
       vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

       const result = await apiFetch('/targets');
       expect(result).toEqual({});
     });

     it('formats FastAPI 422 validation array errors nicely', async () => {
       const mock422Body = {
         detail: [
           {
             loc: ['body', 'url'],
             msg: 'invalid or missing URL scheme',
             type: 'value_error.url',
           },
           {
             loc: ['body', 'name'],
             msg: 'Field required',
             type: 'missing',
           },
         ],
       };
       const mockResponse = new Response(JSON.stringify(mock422Body), {
         status: 422,
         headers: { 'Content-Type': 'application/json' },
       });
       vi.mocked(fetch).mockResolvedValueOnce(mockResponse);

       try {
         await apiFetch('/targets');
       } catch (err: unknown) {
         expect(err).toBeInstanceOf(ApiError);
         const apiError = err as ApiError;
         expect(apiError.status).toBe(422);
         expect(apiError.detail).toBe('body.url: invalid or missing URL scheme; body.name: Field required');
       }
     });
   });
