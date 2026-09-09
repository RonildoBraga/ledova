#import <React/RCTHTTPRequestHandler.h>

@interface LedovaHTTPRequestHandler : RCTHTTPRequestHandler
@end

@implementation LedovaHTTPRequestHandler

RCT_EXPORT_MODULE()

- (float)handlerPriority
{
  return 1;
}

- (id)sendRequest:(NSURLRequest *)request withDelegate:(id<RCTURLRequestDelegate>)delegate
{
  if ([request.URL.scheme.lowercaseString isEqualToString:@"http"]) {
#if DEBUG
    NSArray *hosts = [[NSBundle mainBundle] objectForInfoDictionaryKey:@"LedovaDevelopmentHTTPHosts"];
    if ([hosts containsObject:request.URL.host.lowercaseString]) {
      return [super sendRequest:request withDelegate:delegate];
    }
#endif
    NSURLSessionDataTask *token = [[NSURLSession sharedSession] dataTaskWithRequest:request];
    [token cancel];
    dispatch_async(dispatch_get_main_queue(), ^{
      NSError *error = [NSError errorWithDomain:NSURLErrorDomain
                                          code:NSURLErrorAppTransportSecurityRequiresSecureConnection
                                      userInfo:nil];
      [delegate URLRequest:token didCompleteWithError:error];
    });
    return token;
  }
  return [super sendRequest:request withDelegate:delegate];
}

- (void)URLSession:(NSURLSession *)session
                          task:(NSURLSessionTask *)task
    willPerformHTTPRedirection:(NSHTTPURLResponse *)response
                    newRequest:(NSURLRequest *)request
             completionHandler:(void (^)(NSURLRequest *))completionHandler
{
  completionHandler(nil);
}

@end
