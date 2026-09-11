#import <XCTest/XCTest.h>
#import <React/RCTHTTPRequestHandler.h>
#import <React/RCTURLRequestDelegate.h>

@interface LedovaNetworkCollector : NSObject <RCTURLRequestDelegate>
@property(nonatomic, strong) XCTestExpectation *finished;
@property(nonatomic, strong) NSMutableData *body;
@property(nonatomic, strong) NSURLResponse *response;
@property(nonatomic, strong) NSError *error;
@end

@implementation LedovaNetworkCollector
- (void)URLRequest:(id)token didSendDataWithProgress:(int64_t)bytesSent {}
- (void)URLRequest:(id)token didReceiveResponse:(NSURLResponse *)response { self.response = response; }
- (void)URLRequest:(id)token didReceiveData:(NSData *)data { [self.body appendData:data]; }
- (void)URLRequest:(id)token didCompleteWithError:(NSError *)error
{
  self.error = error;
  [self.finished fulfill];
}
@end

@interface LedovaNetworkTests : XCTestCase
@end

@implementation LedovaNetworkTests
- (NSDictionary *)observe:(RCTHTTPRequestHandler *)handler route:(NSString *)route
{
  NSDictionary *configuration = [[NSBundle mainBundle] objectForInfoDictionaryKey:@"LedovaNetworkProbe"];
  NSURL *url = [NSURL URLWithString:[configuration[@"baseURL"] stringByAppendingString:route]];
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  request.timeoutInterval = 8;
  request.HTTPMethod = @"POST";
  request.HTTPBody = [@"synthetic-local-network-control" dataUsingEncoding:NSUTF8StringEncoding];
  [request setValue:configuration[@"nonce"] forHTTPHeaderField:@"X-Ledova-Probe"];
  [request setValue:configuration[@"run"] forHTTPHeaderField:@"X-Ledova-Probe-Run"];
  LedovaNetworkCollector *collector = [LedovaNetworkCollector new];
  collector.finished = [self expectationWithDescription:route];
  collector.body = [NSMutableData data];
  XCTAssertTrue([handler canHandleRequest:request]);
  id token = [handler sendRequest:request withDelegate:collector];
  XCTAssertNotNil(token);
  [self waitForExpectations:@[collector.finished] timeout:12];
  [handler invalidate];
  NSHTTPURLResponse *response = (NSHTTPURLResponse *)collector.response;
  return @{
    @"handler": NSStringFromClass(handler.class),
    @"status": @(response.statusCode),
    @"body": [[NSString alloc] initWithData:collector.body encoding:NSUTF8StringEncoding] ?: @"",
    @"errorDomain": collector.error.domain ?: @"",
    @"errorCode": @(collector.error.code),
    @"priority": [handler respondsToSelector:@selector(handlerPriority)] ? @([handler handlerPriority]) : @0
  };
}

- (void)testConfiguredPrivateHostThroughTheActualNativeHandler
{
  NSBundle *bundle = [NSBundle mainBundle];
  NSDictionary *configuration = [bundle objectForInfoDictionaryKey:@"LedovaNetworkProbe"];
  XCTAssertNotNil(configuration);
  NSDictionary *baseline = [self observe:[RCTHTTPRequestHandler new] route:@"/baseline"];
  Class actualClass = NSClassFromString(@"LedovaHTTPRequestHandler");
  XCTAssertNotNil(actualClass);
  XCTAssertTrue([actualClass isSubclassOfClass:RCTHTTPRequestHandler.class]);
  if (!actualClass || ![actualClass isSubclassOfClass:RCTHTTPRequestHandler.class]) return;
  NSDictionary *actual = [self observe:[actualClass new] route:@"/handler"];
#if DEBUG
  BOOL debug = YES;
#else
  BOOL debug = NO;
#endif
  NSDictionary *result = @{
    @"mode": configuration[@"mode"],
    @"run": configuration[@"run"],
    @"debug": @(debug),
    @"os": NSProcessInfo.processInfo.operatingSystemVersionString,
    @"bundleIdentifier": bundle.bundleIdentifier,
    @"ats": [bundle objectForInfoDictionaryKey:@"NSAppTransportSecurity"],
    @"developmentHosts": [bundle objectForInfoDictionaryKey:@"LedovaDevelopmentHTTPHosts"] ?: @[],
    @"baseline": baseline,
    @"actual": actual
  };
  NSURL *documents = [[[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask] firstObject];
  NSData *json = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
  XCTAssertTrue([json writeToURL:[documents URLByAppendingPathComponent:@"ledova-debug-network-result.json"] atomically:YES]);
  XCTAssertEqualObjects(actual[@"handler"], @"LedovaHTTPRequestHandler");
  XCTAssertEqualObjects(actual[@"priority"], @1);
  if (debug) {
    XCTAssertEqualObjects(baseline[@"errorDomain"], @"");
    XCTAssertEqualObjects(baseline[@"status"], @200);
    XCTAssertEqualObjects(baseline[@"body"], @"ledova-local-network-control");
  } else if ([baseline[@"errorDomain"] length]) {
    XCTAssertEqualObjects(baseline[@"errorDomain"], NSURLErrorDomain);
    XCTAssertEqualObjects(baseline[@"errorCode"], @(NSURLErrorAppTransportSecurityRequiresSecureConnection));
  } else {
    XCTAssertEqualObjects(baseline[@"status"], @200);
    XCTAssertEqualObjects(baseline[@"body"], @"ledova-local-network-control");
  }
  if ([configuration[@"mode"] isEqualToString:@"configured-debug"]) {
    XCTAssertTrue(debug);
    XCTAssertEqualObjects(actual[@"errorDomain"], @"");
    XCTAssertEqualObjects(actual[@"status"], @200);
    XCTAssertEqualObjects(actual[@"body"], @"ledova-local-network-control");
  } else {
    XCTAssertEqual(debug, [configuration[@"mode"] isEqualToString:@"unconfigured-debug"]);
    XCTAssertEqualObjects(actual[@"errorDomain"], NSURLErrorDomain);
    XCTAssertEqualObjects(actual[@"errorCode"], @(NSURLErrorAppTransportSecurityRequiresSecureConnection));
    XCTAssertEqualObjects(actual[@"status"], @0);
    XCTAssertEqualObjects(actual[@"body"], @"");
  }
}
@end
